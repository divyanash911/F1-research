from __future__ import annotations

from typing import Any, List, Optional, TypedDict

import json
import os
import time
import uuid
import logging
import re

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from .kb import JsonlKnowledgeBase
from .settings import Settings
from .tools import (
    make_kb_tools,
    openf1_drivers,
    openf1_intervals,
    openf1_laps,
    openf1_driver_race_results,
    openf1_driver_stints_across_races,
    openf1_meetings,
    openf1_meetings_for_year,
    openf1_overtakes,
    openf1_pit,
    openf1_positions,
    openf1_race_control,
    openf1_races_for_year,
    openf1_session_result,
    openf1_sessions,
    openf1_stints,
    openf1_team_radio,
    openf1_weather,
    openf1_weather_for_race_sessions,
    web_search,
    scrape_webpage,
    python_repl,
)
from .tools_fastf1 import (
    fastf1_event_schedule,
    fastf1_completed_event_schedule,
    fastf1_session_summary,
    fastf1_driver_pace_overview,
    fastf1_compare_drivers_minisectors,
    fastf1_stint_degradation_summary,
)


class AgentRunResult(TypedDict):
    answer: str
    tool_calls: list[dict[str, Any]]
    grounding_ok: bool
    grounding_issues: list[str]


SYSTEM_PROMPT = (
    "You are an autonomous F1 research assistant designed for deep, meticulous analysis.\n"
    "Your job is to answer questions by gathering evidence using tools. You must act as a true researcher:\n"
    "1. HYPOTHESIZE: Think about what data is needed.\n"
    "2. GATHER SMALL DATA: Use OpenF1 API tools (like sessions, meetings) to get basic IDs and context, or web_search to find news.\n"
    "3. ANALYZE HUGE DATA (DEEP): If handling large OpenF1 datasets (like laps, stints, telemetry, weather), **DO NOT call the OpenF1 tools directly** as it will overflow your context window! Instead, WRITE A PYTHON SCRIPT using `python_repl` that uses `requests` to fetch from `https://api.openf1.org/v1/` and `pandas` to analyze the data.\n"
    "4. READ FULL ARTICLES: If searching for news, use `scrape_webpage` on the most promising web search results to read the full context.\n"
    "5. REFLECT: Synthesize the quantitative and qualitative insights. Take your time to draw profound, unseen conclusions.\n\n"
    "Rules:\n"
    "- Always substantiate claims with concrete statistics (e.g. 'Driver X was 0.2s faster on average in Sector 1' instead of 'Driver X was fast').\n"
    "- Cite your sources (URLs or OpenF1 endpoints).\n"
    "- Do not reveal chain-of-thought in the final output. Provide only concise conclusions and the evidence you used.\n"
    "- If solving a complex problem, take as many steps as needed using tools. Never guess."
)



# ─────────────────────────────────────────────────────────────────────────────
# Grounding guard — catches hallucination signals before they enter the pipeline
# ─────────────────────────────────────────────────────────────────────────────

_HALLUCINATION_PATTERNS: list[tuple[str, str]] = [
    (r"example\.com/",
     "Fabricated example.com URL — web_search was not called"),
    (r"verstappen\'?s strategy",
     "Placeholder \'Verstappen\'s strategy\' — FastF1 returned no real data"),
    (r"bottas.{0,40}(red bull|redbull)|(red bull|redbull).{0,40}bottas",
     "Wrong team: Bottas is at Cadillac in 2026, not Red Bull"),
    (r"hamilton.{0,40}mercedes.*contract|hamilton.{0,40}mercedes.*extension",
     "Wrong team: Hamilton moved to Ferrari for 2025"),
    (r"hamilton.{0,40}mclaren|mclaren.{0,40}hamilton",
     "Wrong team: Hamilton has not been at McLaren since 2012"),
    (r"piastri.{0,40}(red bull|redbull)|(red bull|redbull).{0,40}piastri",
     "Wrong team: Piastri is at McLaren, not Red Bull"),
    (r"(perez|p[eé]rez).{0,40}(red bull|redbull)|(red bull|redbull).{0,40}(perez|p[eé]rez)",
     "Wrong team: Pérez left Red Bull after 2024"),
    (r"[1-9]\d{2,}-?point penalty",
     "Impossible penalty: F1 doesn\'t issue hundred/thousand-point penalties"),
    (r"suzuka 2026.{0,80}(winner|won|victory|finished first)",
     "Future race: Suzuka 2026 has not happened yet"),
]

_TOOL_REQUIRED_KEYWORDS = [
    "news", "standings", "results", "history", "historical",
    "pace", "telemetry", "strategy", "weather", "prediction",
    "race", "qualifying", "driver", "team", "circuit",
]


def _check_grounding(answer: str, tool_calls_made: int, user_message: str) -> tuple[bool, list[str]]:
    issues: list[str] = []
    text_lower = (answer or "").lower()
    msg_lower = (user_message or "").lower()
    for pattern, note in _HALLUCINATION_PATTERNS:
        if re.search(pattern, text_lower):
            issues.append(note)
    needs_tools = any(kw in msg_lower for kw in _TOOL_REQUIRED_KEYWORDS)
    if needs_tools and tool_calls_made == 0:
        issues.append("Zero tool calls for a data task — answer likely hallucinated from training weights")
    return len(issues) == 0, issues


def build_agent(settings: Settings, kb: JsonlKnowledgeBase):
    from langchain_openai import ChatOpenAI
    import httpx
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    provider = (settings.llm_provider or "openrouter").lower()
    if provider == "openrouter":
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter")
        llm = ChatOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=settings.default_model,
            temperature=0.3,
            default_headers={
                # OpenRouter strongly recommends/depends on these headers for request attribution.
                # Without them, OpenRouter can respond with 400 Bad Request.
                "HTTP-Referer": settings.openrouter_http_referer,
                "X-Title": settings.openrouter_x_title,
            },
        )
    elif provider == "ollama":
        ollama_mode = (getattr(settings, "ollama_mode", None) or "openai").lower()

        if ollama_mode == "native":
            # Ollama native endpoint:
            #   POST http://localhost:11434/api/generate
            # Body:
            #   {"model": "...", "prompt": "...", "stream": false}
            class OllamaNativeChatModel(BaseChatModel):
                base_url: str
                model: str
                temperature: float = 0.3
                timeout_s: float = 120.0

                @property
                def _llm_type(self) -> str:  # pragma: no cover
                    return "ollama_native"

                def _messages_to_prompt(self, messages: list[BaseMessage]) -> str:
                    # Minimal, robust prompt format for /api/generate.
                    # Keeps roles visible; works decently for instruction-tuned models.
                    lines: list[str] = []
                    for m in messages:
                        role = getattr(m, "type", None) or m.__class__.__name__.replace("Message", "")
                        content = getattr(m, "content", "")
                        if content is None:
                            content = ""
                        lines.append(f"{role.upper()}: {content}")
                    lines.append("ASSISTANT:")
                    return "\n\n".join(lines)

                def _generate(
                    self,
                    messages: list[BaseMessage],
                    stop: list[str] | None = None,
                    run_manager=None,
                    **kwargs: Any,
                ) -> ChatResult:
                    prompt = self._messages_to_prompt(messages)
                    payload: dict[str, Any] = {
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        # Ollama supports options; keep it light.
                        "options": {"temperature": self.temperature},
                    }

                    url = self.base_url.rstrip("/") + "/api/generate"
                    with httpx.Client(timeout=self.timeout_s) as client:
                        r = client.post(url, json=payload)
                        r.raise_for_status()
                        data = r.json()

                    text = (data.get("response") or "").strip()
                    gen = ChatGeneration(message=AIMessage(content=text))
                    return ChatResult(generations=[gen])

            # In native mode, base_url should be host root, e.g. http://localhost:11434
            native_base = getattr(settings, "ollama_base_url", None) or "http://localhost:11434"
            # If user accidentally left /v1 on the end, strip it.
            if native_base.rstrip("/").endswith("/v1"):
                native_base = native_base.rstrip("/")[:-3]

            llm = OllamaNativeChatModel(
                base_url=native_base,
                model=settings.default_model,
                temperature=0.3,
            )
        else:
            # OpenAI-compatible mode:
            # Ollama serves an OpenAI-compatible API at http://localhost:11434/v1
            # It usually doesn't require an API key, but ChatOpenAI expects one.
            llm = ChatOpenAI(
                api_key=getattr(settings, "ollama_api_key", None) or "ollama",
                base_url=getattr(settings, "ollama_base_url", None) or "http://localhost:11434/v1",
                model=settings.default_model,
                temperature=0.3,
            )
    else:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        llm = ChatOpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            model=settings.default_model,
            temperature=0.3,
        )

    tools: list[BaseTool] = [
        # FastF1 tools (cache-backed)
        fastf1_event_schedule,
        fastf1_completed_event_schedule,
        fastf1_session_summary,
        fastf1_driver_pace_overview,
        fastf1_compare_drivers_minisectors,
        fastf1_stint_degradation_summary,

        openf1_sessions,
        openf1_meetings,
        openf1_meetings_for_year,
        openf1_races_for_year,
        openf1_session_result,
        openf1_driver_race_results,
        openf1_driver_stints_across_races,
        openf1_drivers,
        openf1_positions,
        openf1_laps,
        openf1_stints,
        openf1_weather,
        openf1_weather_for_race_sessions,
        openf1_intervals,
        openf1_pit,
        openf1_overtakes,
        openf1_race_control,
        openf1_team_radio,
        web_search,
        scrape_webpage,
        python_repl,
        *make_kb_tools(kb),
    ]

    # Attach a lightweight error logger for non-2xx OpenRouter/Groq responses.
    # This helps debug cases where upstream returns HTTP 400 but the message is
    # swallowed in higher-level exceptions.
    try:
        from openai import APIStatusError  # type: ignore
    except Exception:  # pragma: no cover
        APIStatusError = None  # type: ignore

    try:
        import logging

        _log = logging.getLogger("f1_agents.llm")
        _orig = getattr(llm, "ainvoke", None)
        if callable(_orig):
            async def _ainvoke_with_logging(*args, **kwargs):  # type: ignore
                try:
                    return await _orig(*args, **kwargs)
                except Exception as e:  # pragma: no cover
                    status = getattr(e, "status_code", None) or getattr(e, "status", None)
                    # OpenAI python SDK attaches response body on APIStatusError
                    if APIStatusError is not None and isinstance(e, APIStatusError):
                        try:
                            body = getattr(getattr(e, "response", None), "text", None)
                            if callable(body):
                                body_text = body()
                            else:
                                body_text = str(body) if body is not None else ""
                            body_text = (body_text or "")
                            if len(body_text) > 2000:
                                body_text = body_text[:2000] + "…"
                            _log.error("LLM API error status=%s body=%s", status, body_text)
                        except Exception:
                            _log.error("LLM API error status=%s (failed to read body)", status)
                    else:
                        _log.error("LLM call failed status=%s err=%s", status, str(e)[:500])
                    raise

            setattr(llm, "ainvoke", _ainvoke_with_logging)
    except Exception:
        # Never fail agent construction due to logging instrumentation.
        pass

    return create_react_agent(llm, tools)  # system prompt injected per-call in run_agent


async def run_agent(
    agent,
    user_message: str,
    extra_system: Optional[str] = None,
) -> AgentRunResult:
    logger = logging.getLogger("f1_agents.agent")
    debug = os.getenv("AGENTS_DEBUG", "0") == "1"
    run_id = uuid.uuid4().hex[:10]
    t0 = time.time()

    logger.info(
        "agent_run_start run_id=%s msg_len=%s extra_system=%s",
        run_id,
        len(user_message or ""),
        bool(extra_system),
    )
    # FIX: Merge into ONE SystemMessage.
    # Sending two SystemMessages causes HTTP 400 on OpenRouter/most providers.
    # When that 400 fired before, LangGraph swallowed the exception and the model
    # answered purely from training weights with zero tool calls — causing all the
    # fabricated URLs, wrong teams, and fake race results seen in agent_thought.log.
    if extra_system:
        merged_system = (
            SYSTEM_PROMPT
            + "\n\n"
            + "─" * 60
            + "\nDEPARTMENT CONTEXT & OUTPUT INSTRUCTIONS:\n"
            + "─" * 60
            + "\n"
            + extra_system
        )
    else:
        merged_system = SYSTEM_PROMPT

    messages: List[BaseMessage] = [
        SystemMessage(content=merged_system),
        HumanMessage(content=user_message),
    ]

    out = await agent.ainvoke({"messages": messages})

    # Log the full chain of thought to a file
    try:
        with open("agent_thought.log", "a", encoding="utf-8") as tf:
            tf.write(f"\n\n{'='*80}\n🚀 RUN ID: {run_id} | {time.strftime('%Y-%m-%d %H:%M:%S')}\n{'='*80}\n")
            for i, msg in enumerate(out.get("messages", [])):
                msg_type = msg.__class__.__name__
                tf.write(f"\n--- 📝 [{i}] {msg_type} ---\n")
                
                # Print content (thoughts/responses)
                if msg.content:
                    # Truncate very long tool responses to 2000 chars for readability
                    content_str = str(msg.content)
                    if msg_type == "ToolMessage" and len(content_str) > 2000:
                        content_str = content_str[:2000] + "... [TRUNCATED]"
                    tf.write(f"{content_str}\n")
                
                # Print tool calls clearly
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tf.write(f"\n🛠️  TOOL CALL: {tc.get('name')}\n")
                        tf.write(f"   ARGS: {json.dumps(tc.get('args', {}), indent=2)}\n")
    except Exception as e:
        logger.error(f"Failed to write agent thoughts: {e}")

    # Collect a light tool trace if available.
    tool_calls: list[dict[str, Any]] = []
    tool_call_keys: set[str] = set()

    def _record_unique_tool_call(tc: Any) -> None:
        if not isinstance(tc, dict):
            return
        key = json.dumps(tc, sort_keys=True, default=str)
        if key in tool_call_keys:
            return
        tool_call_keys.add(key)
        tool_calls.append(tc)

    for m in out.get("messages", []):
        msg_tool_calls = getattr(m, "tool_calls", None) or []
        for tc in msg_tool_calls:
            _record_unique_tool_call(tc)
        additional = getattr(m, "additional_kwargs", None) or {}
        if "tool_calls" in additional:
            for tc in additional["tool_calls"] or []:
                _record_unique_tool_call(tc)

    # Log tool calls (names + args) for visibility. This is NOT chain-of-thought.
    if tool_calls:
        for tc in tool_calls:
            try:
                fn = (tc.get("function") or {}).get("name")
                args = (tc.get("function") or {}).get("arguments")
                if isinstance(args, str):
                    # keep logs readable
                    args_preview = args if len(args) < 1200 else args[:1200] + "…"
                else:
                    args_preview = args
                logger.info("agent_tool_call run_id=%s tool=%s args=%s", run_id, fn, args_preview)
            except Exception:
                logger.info("agent_tool_call run_id=%s tool_call=%s", run_id, tc)

    final_text = ""
    if out.get("messages"):
        final_text = out["messages"][-1].content or ""

    dt_ms = int((time.time() - t0) * 1000)
    logger.info(
        "agent_run_end run_id=%s duration_ms=%s answer_chars=%s tool_calls=%s",
        run_id,
        dt_ms,
        len(final_text),
        len(tool_calls),
    )

    if debug:
        # In debug mode, log the final answer (still no CoT).
        preview = final_text if len(final_text) < 4000 else final_text[:4000] + "…"
        logger.debug("agent_final_answer run_id=%s answer=%s", run_id, preview)

    # Grounding check
    grounding_ok, grounding_issues = _check_grounding(final_text, len(tool_calls), user_message)
    if not grounding_ok:
        strict_grounding = os.getenv("AGENTS_STRICT_GROUNDING", "0") == "1"
        log_fn = logger.error if strict_grounding else logger.warning
        for issue in grounding_issues:
            log_fn("grounding_fail run_id=%s issue=%s", run_id, issue)
        final_text = (
            "__GROUNDING_FAILED__\n"
            "Hallucination signals detected:\n"
            + "\n".join(f"  - {i}" for i in grounding_issues)
            + "\n\nRaw output (do not treat as fact):\n" + final_text
        )
        if strict_grounding:
            raise RuntimeError("Grounding failed: " + "; ".join(grounding_issues))

    # Log grounding result
    logger.info(
        "agent_run_end run_id=%s duration_ms=%s answer_chars=%s tool_calls=%s grounding_ok=%s",
        run_id, int((time.time() - t0) * 1000), len(final_text), len(tool_calls), grounding_ok,
    )

    return {"answer": final_text, "tool_calls": tool_calls, "grounding_ok": grounding_ok, "grounding_issues": grounding_issues}


# ─────────────────────────────────────────────────────────────────────────────
# Hallucination guard for enrichment outputs
# ─────────────────────────────────────────────────────────────────────────────

_HALLUCINATION_SIGNATURES = [
    "example.com",
    "verstappen's strategy",
    "flawless strategy",
    "2000-point penalty",
    "1500-point penalty",
]

_REQUIRED_NON_EMPTY: dict[str, list[str]] = {
    "context.recent_results":        ["races"],
    "context.standings":             ["wdc", "wcc"],
    "context.historical_same_track": ["seasons"],
    "context.telemetry_season_trend":["trends"],
}


def _find_field(obj: Any, field: str) -> Any:
    if not isinstance(obj, dict):
        return None
    if field in obj:
        return obj[field]
    for v in obj.values():
        result = _find_field(v, field)
        if result is not None:
            return result
    return None


def validate_enrichment_output(state_key: str, value: dict) -> tuple[bool, str]:
    """
    Returns (is_valid, reason).
    Rejects enrichment outputs that show hallucination signatures before they
    are stored in state and fed to the Research Director.
    """
    if not isinstance(value, dict):
        return False, "output is not a dict"

    text = json.dumps(value).lower()

    for sig in _HALLUCINATION_SIGNATURES:
        if sig.lower() in text:
            return False, f"hallucination signature detected: '{sig}'"

    required = _REQUIRED_NON_EMPTY.get(state_key, [])
    for field in required:
        found = _find_field(value, field)
        if found is None:
            return False, f"required field '{field}' missing"
        if isinstance(found, list) and len(found) == 0:
            return False, f"required field '{field}' is empty — tool call likely failed"

    if state_key == "context.standings":
        standings_val = value.get("standings") or value
        if "query" in standings_val and "wdc" not in standings_val:
            return False, "standings contains only search query, not actual data"

    return True, "ok"
