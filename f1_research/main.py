"""
F1 Research Program - Main Autonomous Research Engine

The core orchestration loop:
1. Fetches current F1 context (news, schedule)
2. Runs deep telemetry analysis on recent race
3. Runs strategy & constructor analysis
4. Runs driver form & anomaly detection
5. Runs race predictions
6. Synthesizes everything into intelligence report
7. Repeats on schedule or on demand

Run: python main.py
     python main.py --event "Bahrain" --session R
     python main.py --mode single --crew telemetry
     python main.py --mode loop --interval 6
"""

import sys
import os
import argparse
import time
import json
import traceback
import random
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from crewai.tasks.task_output import TaskOutput

# Load env first
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

# ── Disable CrewAI telemetry (prevents timeout spam in logs) ────────────────
os.environ["OTEL_SDK_DISABLED"]        = "true"
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "agents"))
sys.path.insert(0, str(Path(__file__).parent / "crews"))
sys.path.insert(0, str(Path(__file__).parent / "tools"))

# Initialize logging (must be before other imports)
from logger import (
    print_banner, console, log_research_summary, log_error,
    log_insight, log_agent_message, log_llm_request, log_llm_response,
    log_telemetry_analysis, log_task_event, log_task_summary,
    set_task_context, get_task_context, clear_task_context,
    SESSION_ID, SESSION_DIR, Colors
)

# Initialize CrewAI event callbacks (best-effort)
try:
    from callbacks import setup_callbacks
    setup_callbacks()
except Exception:
    # Non-fatal: execution should continue even if event hooks can't be registered.
    pass

from llm_config import get_backend_info, get_backend_order, set_backend
from agents.f1_agents import make_agents
from run_state import RunState, TaskCheckpoint
from crews.research_crews import (
    build_news_crew,
    build_telemetry_crew,
    build_strategy_crew,
    build_driver_anomaly_crew,
    build_prediction_crew,
    build_synthesis_crew,
)


# ── Research Session Tracker ────────────────────────────────────────────────
class ResearchSession:
    def __init__(self):
        self.start_time    = datetime.now()
        self.crews_run     = []
        self.insights_count = 0
        self.errors        = []
        self.recent_event  = "1"  # default, will be updated

    def log_crew_complete(self, crew_name: str, duration_s: float, success: bool):
        self.crews_run.append({
            "crew":     crew_name,
            "duration": round(duration_s, 1),
            "success":  success,
        })
        status = "✅" if success else "❌"
        console.info(
            f"{status} {Colors.CYAN}{crew_name}{Colors.RESET} completed in "
            f"{Colors.YELLOW}{duration_s:.1f}s{Colors.RESET}"
        )

    def final_summary(self) -> dict:
        elapsed = (datetime.now() - self.start_time).total_seconds()
        return {
            "session_id":    SESSION_ID,
            "started":       self.start_time.isoformat(),
            "duration_min":  round(elapsed / 60, 1),
            "crews_run":     self.crews_run,
            "errors_count":  len(self.errors),
            "errors":        self.errors[:5],
            "insights_dir":  "insights/",
            "log_dir":       str(SESSION_DIR),
        }


# ── Crew runner with error handling ────────────────────────────────────────
def _fallback_insight_type(crew_name: str) -> str:
    name = crew_name.lower()
    if "telemetry" in name:
        return "telemetry_finding"
    if "predict" in name:
        return "race_prediction"
    if "strategy" in name:
        return "strategy_insight"
    if "driver" in name or "anomaly" in name:
        return "driver_analysis"
    if "news" in name:
        return "technical_discovery"
    return "trend_analysis"


def _compact_json_value(value, depth: int = 0):
    if depth >= 2:
        if isinstance(value, list):
            return f"<list len={len(value)}>"
        if isinstance(value, dict):
            return f"<dict keys={list(value.keys())[:5]}>"
        return value
    if isinstance(value, dict):
        out = {}
        for idx, (k, v) in enumerate(value.items()):
            if idx >= 8:
                out["_truncated"] = f"{len(value) - 8} more keys"
                break
            out[k] = _compact_json_value(v, depth + 1)
        return out
    if isinstance(value, list):
        return [_compact_json_value(v, depth + 1) for v in value[:5]] + ([f"... {len(value) - 5} more items"] if len(value) > 5 else [])
    return value


def _compact_text_payload(text: str, max_chars: int = 1800) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
        compact = _compact_json_value(parsed)
        rendered = json.dumps(compact, indent=2)
        if len(rendered) <= max_chars:
            return rendered
        return rendered[: max_chars - 40].rstrip() + "\n... <truncated>"
    except Exception:
        if len(text) <= max_chars:
            return text
        head = text[: int(max_chars * 0.75)].rstrip()
        tail = text[-int(max_chars * 0.15):].lstrip()
        return f"{head}\n...\n{tail}"


def _compact_task_output(task_output: TaskOutput, max_chars: int = 1800) -> TaskOutput:
    compact_raw = _compact_text_payload(task_output.raw or str(task_output), max_chars=max_chars)
    compact_summary = _compact_text_payload(task_output.summary or compact_raw, max_chars=min(700, max_chars))
    return TaskOutput(
        description=task_output.description,
        name=task_output.name,
        expected_output=task_output.expected_output,
        summary=compact_summary,
        raw=compact_raw,
        pydantic=None,
        json_dict=None,
        agent=task_output.agent,
        output_format=task_output.output_format,
    )


def _extract_preloaded_memory_preview(text: str, max_chars: int = 1000) -> str:
    marker = "Preloaded memory for this task"
    idx = (text or "").find(marker)
    if idx == -1:
        return ""
    preview = text[idx:].strip()
    next_section = preview.find("\n\n")
    if next_section != -1 and next_section > 0:
        preview = preview[: max(next_section + 1, min(len(preview), max_chars))]
    return preview[:max_chars].strip()


def _publish_task_checkpoint(crew_name: str, task_index: int, description: str, agent_role: str, compact_output: str) -> None:
    if os.getenv("PUBLISH_TASK_CHECKPOINTS", "true").lower() not in {"1", "true", "yes", "on"}:
        return
    content = (
        f"**Crew:** {crew_name}\n"
        f"**Task:** {task_index + 1}\n"
        f"**Agent:** {agent_role}\n\n"
        f"**Task Description Preview:** {description[:300]}\n\n"
        f"## Checkpoint Summary\n\n{compact_output or '_No output captured._'}"
    )
    log_insight(
        _fallback_insight_type(crew_name),
        f"{crew_name} Task {task_index + 1} Checkpoint",
        content,
        confidence=0.45,
        tags=["checkpoint", crew_name.lower().replace(" ", "_"), f"task_{task_index + 1}"],
    )


def _publish_fallback_from_checkpoints(crew_name: str, run_state: RunState, last_exc: Exception | None) -> bool:
    tasks = run_state.completed_tasks()
    if not tasks:
        return False

    sections = []
    for task in tasks:
        preview = (task.get("description_preview") or "Task").strip()
        output = (task.get("output") or "").strip()
        output = output[:1600]
        sections.append(
            f"### Completed Task {task.get('index', '?') + 1}: {preview}\n"
            f"**Agent:** {task.get('agent_role', 'Unknown')}\n\n"
            f"{output or '_No output captured._'}"
        )

    error_line = str(last_exc) if last_exc else "Unknown failure"
    content = (
        "This insight was assembled from completed task checkpoints after the crew failed "
        "before its final synthesis step.\n\n"
        f"**Failure:** {error_line[:300]}\n\n"
        "## Recovered Findings\n\n"
        f"{chr(10).join(sections)}\n\n"
        "## Reliability Note\n\n"
        "- Completed tasks are preserved verbatim from the run checkpoint.\n"
        "- Missing later tasks may reduce synthesis quality, but recovered findings remain usable evidence.\n"
    )
    log_insight(
        _fallback_insight_type(crew_name),
        f"{crew_name} - Recovered Findings",
        content,
        confidence=0.55,
        tags=["fallback", "checkpoint_recovery", crew_name.lower().replace(" ", "_")],
    )
    return True


def _is_empty_llm_response_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    # CrewAI / LiteLLM variants we have observed
    needles = [
        "none or empty",
        "invalid response from llm call",
        "received none",
        "empty response",
    ]
    return any(n in msg for n in needles)


def run_crew_safe(crew, crew_name: str, session: ResearchSession, rebuild_crew_fn=None):
    """Run a crew with full error handling, timing, and logging."""
    start = time.time()
    console.info(f"\n{'═'*60}")
    console.info(f"🚀 Starting Crew: {Colors.BOLD}{crew_name}{Colors.RESET}")
    console.info(f"{'═'*60}")
    
    # Resilience params (agent-level retry budget)
    max_attempts = int(os.getenv("CREW_RETRY_MAX_ATTEMPTS", "3"))
    max_elapsed_s = int(os.getenv("CREW_RETRY_MAX_ELAPSED_S", "240"))
    base_backoff_s = float(os.getenv("CREW_RETRY_BACKOFF_S", "2"))

    attempt = 0
    last_exc: Exception | None = None
    kickoff_started = time.time()

    # Task-level persistence: ensures we don't lose completed work if the crew crashes.
    # We checkpoint after each Task completes and can resume from the next task.
    run_state = RunState(base_dir=Path("logs"), session_id=SESSION_ID, crew_name=crew_name)

    # Provider rotation (only used for the "None or empty" LLM response class of failures)
    provider_order = get_backend_order()
    provider_idx = 0
    conservative_mode = False

    while attempt < max_attempts and (time.time() - kickoff_started) < max_elapsed_s:
        attempt += 1
        try:
            if attempt > 1:
                console.warning(
                    f"🔁 Retrying {crew_name} (attempt {attempt}/{max_attempts}) after failure..."
                )
            # Resume logic: if we have checkpoints, skip tasks already completed.
            completed = run_state.completed_task_count()
            if completed > 0:
                console.info(
                    f"🧠 Resuming {crew_name} from checkpoint: skipping {completed}/{len(getattr(crew, 'tasks', []) or [])} tasks"
                )

            # Execute tasks sequentially ourselves so we can checkpoint at boundaries.
            # This avoids having to modify CrewAI internals.
            tasks = list(getattr(crew, "tasks", []) or [])
            final_result = None
            if tasks:
                for i, task in enumerate(tasks):
                    if i < completed:
                        continue
                    agent = getattr(task, "agent", None)
                    agent_role = getattr(agent, "role", "Unknown") if agent else "Unknown"
                    desc = (getattr(task, "description", "") or "").strip()
                    expected = getattr(task, "expected_output", "") or ""
                    llm_model = getattr(getattr(agent, "llm", None), "model", "unknown")
                    preloaded_memory_preview = _extract_preloaded_memory_preview(desc)
                    task_context = {
                        "crew": crew_name,
                        "task_index": i + 1,
                        "agent_role": agent_role,
                        "llm_model": llm_model,
                        "had_preloaded_memory": bool(preloaded_memory_preview),
                        "preloaded_memory_preview": preloaded_memory_preview[:500],
                    }
                    set_task_context(task_context)

                    log_agent_message(
                        agent_name=agent_role,
                        message_type="TASK_START",
                        content=desc[:4000],
                    )
                    log_llm_request(
                        agent_name=agent_role,
                        model=llm_model,
                        prompt_tokens=0,
                        system_prompt=getattr(agent, "instructions", "")[:1200] if agent else "",
                        user_message=desc[:4000],
                    )
                    log_task_event("task_start", {
                        **get_task_context(),
                        "expected_output_preview": expected[:500],
                        "description_preview": desc[:1200],
                    })

                    # Execute a single task
                    try:
                        task_output = task.execute_sync()
                    except Exception as task_exc:
                        log_agent_message(
                            agent_name=agent_role,
                            message_type="TASK_ERROR",
                            content=f"{type(task_exc).__name__}: {str(task_exc)[:4000]}",
                        )
                        log_llm_response(
                            agent_name=agent_role,
                            model=llm_model,
                            response=f"TASK_ERROR: {type(task_exc).__name__}: {str(task_exc)[:4000]}",
                        )
                        log_task_event("task_error", {
                            **get_task_context(),
                            "error_type": type(task_exc).__name__,
                            "error_message": str(task_exc)[:1000],
                        })
                        clear_task_context()
                        raise
                    compact_output = _compact_task_output(task_output)
                    task.output = compact_output
                    final_result = compact_output
                    task_meta = get_task_context()
                    tools_used = list(task_meta.get("tools_used", []))

                    log_agent_message(
                        agent_name=agent_role,
                        message_type="TASK_COMPLETE",
                        content=(compact_output.raw or str(compact_output))[:4000],
                    )
                    log_llm_response(
                        agent_name=agent_role,
                        model=llm_model,
                        response=(compact_output.raw or str(compact_output))[:4000],
                    )
                    if "telemetry" in crew_name.lower() or "telemetry" in agent_role.lower():
                        log_telemetry_analysis(
                            analysis_type=f"{crew_name} Task {i + 1}",
                            session_info=f"event={session.recent_event} | agent={agent_role}",
                            findings=(compact_output.raw or str(compact_output))[:4000],
                            metrics={
                                "task_index": i + 1,
                                "expected_output_preview": expected[:300],
                                "had_preloaded_memory": "Preloaded memory for this task" in desc,
                                "tools_used": tools_used,
                            },
                        )
                    log_task_event("task_complete", {
                        **task_meta,
                        "expected_output_preview": expected[:500],
                        "output_preview": (compact_output.raw or str(compact_output))[:1200],
                    })
                    log_task_summary(
                        crew_name=crew_name,
                        task_index=i,
                        agent_role=agent_role,
                        summary={
                            "had_preloaded_memory": bool(preloaded_memory_preview),
                            "preloaded_memory_preview": preloaded_memory_preview[:500],
                            "tools_used": tools_used,
                            "output_preview": (compact_output.raw or str(compact_output))[:1000],
                        },
                    )

                    # Persist checkpoint
                    desc = desc.replace("\n", " ")
                    run_state.mark_task_complete(
                        TaskCheckpoint(
                            index=i,
                            description_preview=desc[:160],
                            agent_role=agent_role,
                            output=compact_output.raw,
                            had_preloaded_memory="Preloaded memory for this task" in desc,
                            preloaded_memory_preview=preloaded_memory_preview[:500],
                            tools_used=tools_used,
                        )
                    )
                    _publish_task_checkpoint(crew_name, i, desc, agent_role, compact_output.raw)
                    clear_task_context()
            else:
                # Fallback to default behavior if tasks aren't accessible
                final_result = crew.kickoff()

            result = final_result
            duration = time.time() - start
            session.log_crew_complete(crew_name, duration, success=True)

            # Log crew output
            output_str = str(result) if result else "No output"
            console.info(f"📤 {crew_name} Output Preview:\n{output_str[:300]}...")
            return result

        except KeyboardInterrupt:
            # Respect manual stop immediately
            raise

        except Exception as e:
            clear_task_context()
            last_exc = e

            # If the backend returned an empty/None response, rotate providers and rebuild.
            if _is_empty_llm_response_error(e) and rebuild_crew_fn is not None:
                if not conservative_mode:
                    conservative_mode = True
                    current_backend = provider_order[provider_idx]
                    console.warning(
                        "🧯 LLM returned empty output. Rebuilding the same backend in conservative small-model mode."
                    )
                    try:
                        set_backend(current_backend)
                        crew = rebuild_crew_fn(current_backend, conservative=True)
                        continue
                    except Exception as rebuild_exc:
                        log_error(crew_name, rebuild_exc, f"Failed to rebuild {current_backend} in conservative mode")

                if provider_idx + 1 < len(provider_order):
                    provider_idx += 1
                    next_backend = provider_order[provider_idx]
                    console.warning(
                        f"🧯 LLM returned empty output. Switching backend → {Colors.CYAN}{next_backend.upper()}{Colors.RESET}"
                    )
                    try:
                        set_backend(next_backend)
                        # Rebuild the crew with new agents bound to the new backend.
                        crew = rebuild_crew_fn(next_backend, conservative=True)
                        continue
                        # Continue loop (do not consume additional elapsed budget beyond this attempt)
                    except Exception as rebuild_exc:
                        # If rebuild failed (missing key, model not available, etc.), log and keep original error path.
                        log_error(crew_name, rebuild_exc, f"Failed to rebuild crew for backend {next_backend}")
                else:
                    console.error(
                        "🧯 LLM returned empty output and all configured providers were exhausted. "
                        "Check provider health / API keys / rate limits."
                    )

            # Record the error but keep trying within budget
            error_msg = f"{type(e).__name__}: {str(e)[:200]}"
            session.errors.append({"crew": crew_name, "attempt": attempt, "error": error_msg})
            log_error(crew_name, e, f"Crew attempt {attempt} failed")
            console.error(f"❌ {crew_name} attempt {attempt} failed: {error_msg[:120]}")

            # Backoff with jitter, but don't exceed overall budget
            if attempt < max_attempts:
                sleep_s = base_backoff_s * (2 ** (attempt - 1))
                sleep_s = min(sleep_s, 30.0)
                sleep_s = sleep_s + random.uniform(0, 0.5)
                remaining = max_elapsed_s - (time.time() - kickoff_started)
                if remaining > 0:
                    time.sleep(min(sleep_s, remaining))

    # Exhausted retries
    duration = time.time() - start
    session.log_crew_complete(crew_name, duration, success=False)
    recovered = _publish_fallback_from_checkpoints(crew_name, run_state, last_exc)
    if last_exc is not None:
        error_msg = f"{type(last_exc).__name__}: {str(last_exc)[:200]}"
        console.error(f"❌ {crew_name} failed after {attempt} attempts: {error_msg[:120]}")
        console.error(f"   Full trace in: {SESSION_DIR}/errors.log")
        if recovered:
            console.warning("🩹 Published recovered findings from completed checkpoints.")
    return None


# ── Detect most recent race event ───────────────────────────────────────────
def detect_recent_event() -> str:
    """Auto-detect the most recent completed F1 race round number."""
    try:
        import fastf1
        import pandas as pd
        
        season = int(os.getenv("F1_SEASON", "2026"))
        schedule = fastf1.get_event_schedule(season)
        now = pd.Timestamp.now(tz="UTC")
        
        # Events where the race (Session5) has already happened
        past = schedule[schedule["Session5Date"] < now].sort_values("Session5Date")
        
        if past.empty:
            console.warning("⚠️  No completed races found — using round 1")
            return "1"
        
        most_recent = past.iloc[-1]
        round_num   = str(int(most_recent["RoundNumber"]))
        event_name  = most_recent["EventName"]
        console.info(f"🎯 Auto-detected most recent race: Round {round_num} — {event_name}")
        return round_num
    
    except Exception as e:
        console.warning(f"⚠️  Could not detect recent event: {e}. Using round 1.")
        return "1"


# ── Full Research Cycle ──────────────────────────────────────────────────────
def run_full_research(event: str = None, mode: str = "full", specific_crew: str = None):
    """
    Run a complete F1 research cycle.
    
    Args:
        event: Race round number or name (auto-detected if None)
        mode:  'full' (all crews) | 'quick' (news+telemetry+predict) | 'single' (one crew)
        specific_crew: Which crew to run in 'single' mode
    """
    session = ResearchSession()
    print_banner()
    
    # Backend info
    info = get_backend_info()
    console.info(f"🔧 Backend: {Colors.CYAN}{info['backend'].upper()}{Colors.RESET}")
    console.info(f"🔧 Model:   {Colors.CYAN}{info['main_model']}{Colors.RESET}")
    console.info(f"🔧 Season:  {Colors.CYAN}{info['f1_season']}{Colors.RESET}")
    console.info(f"🔧 Mode:    {Colors.CYAN}{mode}{Colors.RESET}")
    console.info("")
    
    # Detect event
    if event is None:
        event = detect_recent_event()
    session.recent_event = event
    console.info(f"📍 Target Event: {Colors.GREEN}{event}{Colors.RESET}\n")
    
    # Build agents (shared across crews)
    console.info("🤖 Initializing research agents...")
    try:
        agents = make_agents()
        console.info(f"✅ {len(agents)} agents initialized\n")
    except Exception as e:
        log_error("MAIN", e, "Failed to initialize agents")
        console.error(f"❌ Agent initialization failed: {e}")
        console.error("Check your LLM_BACKEND and API keys in .env")
        sys.exit(1)

    # Helpers to rebuild crews with a different backend (used for provider fallback)
    def rebuild_agents(backend: str, conservative: bool = False) -> dict:
        return make_agents(backend=backend, conservative=conservative)

    def rebuild_news_crew(backend: str, conservative: bool = False):
        a = rebuild_agents(backend, conservative=conservative)
        c, _ = build_news_crew(a)
        return c

    def rebuild_telemetry_crew(backend: str, conservative: bool = False):
        a = rebuild_agents(backend, conservative=conservative)
        c, _ = build_telemetry_crew(a, event)
        return c

    def rebuild_strategy_crew(backend: str, conservative: bool = False):
        a = rebuild_agents(backend, conservative=conservative)
        c, _ = build_strategy_crew(a, event)
        return c

    def rebuild_driver_crew(backend: str, conservative: bool = False):
        a = rebuild_agents(backend, conservative=conservative)
        c, _ = build_driver_anomaly_crew(a, event)
        return c

    def rebuild_prediction_crew(backend: str, conservative: bool = False):
        a = rebuild_agents(backend, conservative=conservative)
        c, _ = build_prediction_crew(a, event)
        return c

    def rebuild_synthesis_crew(backend: str, conservative: bool = False):
        a = rebuild_agents(backend, conservative=conservative)
        c, _ = build_synthesis_crew(a)
        return c

    # ── CREW EXECUTION PLAN ─────────────────────────────────────────────
    
    if mode == "single" and specific_crew:
        # Run just one specified crew
        crew_map = {
            "news":      lambda: build_news_crew(agents),
            "telemetry": lambda: build_telemetry_crew(agents, event),
            "strategy":  lambda: build_strategy_crew(agents, event),
            "drivers":   lambda: build_driver_anomaly_crew(agents, event),
            "predict":   lambda: build_prediction_crew(agents, event),
            "synthesis": lambda: build_synthesis_crew(agents),
        }
        if specific_crew in crew_map:
            crew, _ = crew_map[specific_crew]()
            rebuild_map = {
                "news": rebuild_news_crew,
                "telemetry": rebuild_telemetry_crew,
                "strategy": rebuild_strategy_crew,
                "drivers": rebuild_driver_crew,
                "predict": rebuild_prediction_crew,
                "synthesis": rebuild_synthesis_crew,
            }
            run_crew_safe(crew, specific_crew, session, rebuild_crew_fn=rebuild_map.get(specific_crew))
        else:
            console.error(f"Unknown crew: {specific_crew}. Options: {list(crew_map.keys())}")

    elif mode == "quick":
        # News → Telemetry → Predictions
        news_crew, _  = build_news_crew(agents)
        tel_crew, _   = build_telemetry_crew(agents, event)
        pred_crew, _  = build_prediction_crew(agents, event)
        
        run_crew_safe(news_crew, "News & Context", session, rebuild_crew_fn=rebuild_news_crew)
        run_crew_safe(tel_crew,  "Telemetry Analysis", session, rebuild_crew_fn=rebuild_telemetry_crew)
        run_crew_safe(pred_crew, "Race Prediction", session, rebuild_crew_fn=rebuild_prediction_crew)

    else:
        # FULL: all 6 crews in sequence
        # Phase 1: Context gathering
        console.info(f"\n{'🏁'*20}")
        console.info("PHASE 1: NEWS & CONTEXT")
        console.info(f"{'🏁'*20}")
        news_crew, _ = build_news_crew(agents)
        run_crew_safe(news_crew, "News & Context Crew", session, rebuild_crew_fn=rebuild_news_crew)

        # Phase 2: Telemetry deep dive
        console.info(f"\n{'📊'*20}")
        console.info("PHASE 2: DEEP TELEMETRY ANALYSIS")
        console.info(f"{'📊'*20}")
        tel_crew, _ = build_telemetry_crew(agents, event)
        run_crew_safe(tel_crew, "Telemetry Deep Dive Crew", session, rebuild_crew_fn=rebuild_telemetry_crew)

        # Phase 3: Strategy & constructors
        console.info(f"\n{'🏎️ '*10}")
        console.info("PHASE 3: STRATEGY & CONSTRUCTOR ANALYSIS")
        console.info(f"{'🏎️ '*10}")
        strat_crew, _ = build_strategy_crew(agents, event)
        run_crew_safe(strat_crew, "Strategy & Constructor Crew", session, rebuild_crew_fn=rebuild_strategy_crew)

        # Phase 4: Driver form & anomalies
        console.info(f"\n{'🔍'*20}")
        console.info("PHASE 4: DRIVER FORM & ANOMALY DETECTION")
        console.info(f"{'🔍'*20}")
        driver_crew, _ = build_driver_anomaly_crew(agents, event)
        run_crew_safe(driver_crew, "Driver & Anomaly Crew", session, rebuild_crew_fn=rebuild_driver_crew)

        # Phase 5: Predictions
        console.info(f"\n{'🔮'*20}")
        console.info("PHASE 5: RACE PREDICTIONS")
        console.info(f"{'🔮'*20}")
        pred_crew, _ = build_prediction_crew(agents, event)
        run_crew_safe(pred_crew, "Prediction Crew", session, rebuild_crew_fn=rebuild_prediction_crew)

        # Phase 6: Synthesis
        console.info(f"\n{'⭐'*20}")
        console.info("PHASE 6: SYNTHESIS & INTELLIGENCE REPORT")
        console.info(f"{'⭐'*20}")
        synth_crew, _ = build_synthesis_crew(agents)
        run_crew_safe(synth_crew, "Synthesis Crew", session, rebuild_crew_fn=rebuild_synthesis_crew)

    # ── Final summary ───────────────────────────────────────────────────
    summary = session.final_summary()
    log_research_summary(summary)
    
    console.info(f"\n{'═'*60}")
    console.info(f"✅ {Colors.GREEN}Research Session Complete{Colors.RESET}")
    console.info(f"{'═'*60}")
    console.info(f"⏱️  Total Duration: {Colors.CYAN}{summary['duration_min']} minutes{Colors.RESET}")
    console.info(f"📊 Crews Run:      {Colors.CYAN}{len(summary['crews_run'])}{Colors.RESET}")
    console.info(f"❌ Errors:         {Colors.RED if summary['errors_count'] > 0 else Colors.GREEN}{summary['errors_count']}{Colors.RESET}")
    console.info(f"💡 Insights:       {Colors.YELLOW}insights/ directory{Colors.RESET}")
    console.info(f"📁 Full Logs:      {Colors.YELLOW}{SESSION_DIR}{Colors.RESET}")
    console.info(f"{'═'*60}\n")
    
    # List published insight files
    insights_dir = Path("insights")
    if insights_dir.exists():
        files = list(insights_dir.glob("*.md"))
        if files:
            console.info("📁 Published Insights:")
            for f in sorted(files)[-5:]:
                console.info(f"   └─ {f.name}")
    
    return summary


# ── Autonomous Loop Mode ─────────────────────────────────────────────────────
def run_autonomous_loop(interval_hours: float = 6, event: str = None):
    """
    Run the research program continuously, re-running every N hours.
    Perfect for 24/7 autonomous F1 research during a race weekend.
    """
    console.info(f"🔄 Starting AUTONOMOUS LOOP mode (interval: {interval_hours}h)")
    console.info("   Press Ctrl+C to stop gracefully\n")
    
    cycle = 0
    while True:
        cycle += 1
        console.info(f"\n{'🏁'*30}")
        console.info(f"AUTONOMOUS RESEARCH CYCLE #{cycle}")
        console.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        console.info(f"{'🏁'*30}\n")
        
        # Re-detect event each cycle (race weekend might change)
        current_event = event or detect_recent_event()
        
        try:
            run_full_research(event=current_event, mode="full")
        except KeyboardInterrupt:
            console.info("\n🛑 Graceful shutdown requested.")
            break
        except Exception as e:
            log_error("AUTONOMOUS_LOOP", e, f"Cycle {cycle} failed")
            console.error(f"❌ Cycle {cycle} error: {e}")
        
        next_run = datetime.now() + timedelta(hours=interval_hours)
        console.info(f"\n💤 Next run at: {Colors.CYAN}{next_run.strftime('%H:%M:%S')}{Colors.RESET}")
        console.info(f"   Sleeping for {interval_hours * 3600:.0f} seconds...")
        
        try:
            time.sleep(interval_hours * 3600)
        except KeyboardInterrupt:
            console.info("\n🛑 Loop interrupted by user.")
            break


# ── CLI ──────────────────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="F1 Autonomous Research Program",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                  # Full research on most recent race
  python main.py --event 1                       # Research on round 1 (Bahrain)
  python main.py --event "Monaco"                # Research on Monaco GP
  python main.py --mode quick                    # Quick analysis (3 crews)
  python main.py --mode single --crew telemetry  # Just telemetry analysis
  python main.py --mode single --crew predict    # Just predictions
  python main.py --mode loop --interval 6        # Autonomous loop every 6 hours
  
Crew options for --crew: news | telemetry | strategy | drivers | predict | synthesis
        """
    )
    parser.add_argument("--event",    default=None,    help="Race round number or name")
    parser.add_argument("--mode",     default="full",  choices=["full", "quick", "single", "loop"])
    parser.add_argument("--crew",     default=None,    help="Specific crew (for --mode single)")
    parser.add_argument("--interval", default=6.0,     type=float, help="Hours between loop cycles")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    if args.mode == "loop":
        run_autonomous_loop(interval_hours=args.interval, event=args.event)
    else:
        run_full_research(
            event=args.event,
            mode=args.mode,
            specific_crew=args.crew,
        )
