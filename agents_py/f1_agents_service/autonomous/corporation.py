"""
corp.py  (v2 — Research Director architecture)
───────────────────────────────────────────────
Replaces the naive fixed-pipeline with:

  1. ResearchDirector  — reads all signals, generates a fresh agenda every cycle
  2. SpecialistAgents  — one per question, free tool usage, iterative exploration
  3. DebateCoordinator — specialists challenge each other's findings
  4. PredictionSynthesizer — final probabilistic race predictions
  5. Publisher/Verifier — unchanged surface API, richer content underneath

Key changes vs v1:
  - No fixed prompt templates. Director rewrites the agenda each run.
  - Specialists loop (up to MAX_EXPLORATION_ROUNDS) until confident.
  - Cross-department debate before publishing.
  - Prediction layer is a first-class output with structured probabilities.
  - Same-track historical comparison is always included in context.
  - Weather is surfaced to EVERY specialist, not just the weather job.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from ..agent_graph import build_agent, run_agent, validate_enrichment_output
from ..kb import JsonlKnowledgeBase
from ..settings import Settings
from .artifacts import ArtifactStore
from .departments import (
    compute_next_race_openf1,
    persist_department_snapshot,
    summarize_weather_openf1,
)
from .jobs import DEFAULT_JOBS, JobType
from .scheduler import JobScheduler
from .state_store import StateStore
from .store import InsightStore
from .types import InsightBundle

# New architecture modules (same package)
from .research_director import (
    ResearchAgenda,
    ResearchQuestion,
    build_director_prompt,
    parse_agenda,
    _DIRECTOR_SYSTEM,
)
from .specialist_agents import (
    SpecialistFinding,
    DebateChallenge,
    DebateResult,
    DEPT_SYSTEMS,
    build_specialist_prompt,
    build_debate_prompt,
    build_resolution_prompt,
    parse_specialist_finding,
    parse_debate_challenge,
    parse_resolution,
)

logger = logging.getLogger("f1_agents.corp")

# ── tunables ──────────────────────────────────────────────────────────────────
MAX_EXPLORATION_ROUNDS   = int(os.getenv("CORP_MAX_EXPLORATION_ROUNDS", "3"))
MAX_FOLLOW_UP_QUESTIONS  = int(os.getenv("CORP_MAX_FOLLOW_UP_QUESTIONS", "4"))
DEBATE_ROUNDS            = int(os.getenv("CORP_DEBATE_ROUNDS", "1"))   # 0 = skip debate
SPECIALIST_CONCURRENCY   = int(os.getenv("CORP_SPECIALIST_CONCURRENCY", "3"))
MAX_SPECIALIST_TIMEOUT_SECONDS = int(os.getenv("CORP_MAX_SPECIALIST_TIMEOUT_SECONDS", "180"))
# Filters out trivial fragments like "why?" while allowing normal sentence-like prompts.
MIN_FOLLOW_UP_QUESTION_LENGTH = 10
# ─────────────────────────────────────────────────────────────────────────────


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_json_candidate(text: str) -> str:
    import re
    text = (text or "").strip()
    if not text:
        return "{}"
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        return m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def _safe_json(text: str, fallback: dict[str, Any]) -> dict[str, Any]:
    raw = _extract_json_candidate(text)
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
        return fallback
    except Exception:
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot builder — assembles everything the Director needs in one dict
# ─────────────────────────────────────────────────────────────────────────────

def _build_knowledge_snapshot(state: StateStore) -> dict[str, Any]:
    """Pull all available state keys into a single snapshot for the Director."""
    def _get(key: str) -> Any:
        row = state.get(key)
        return row.value if row else None

    return {
        "next_race":              _get("context.next_race"),
        "weather_forecast":       _get("context.weather"),
        "recent_results":         _get("context.recent_results"),
        "standings":              _get("context.standings"),
        "historical_same_track":  _get("context.historical_same_track"),
        "telemetry_season_trend": _get("context.telemetry_season_trend"),
        "news_signals":           _get("signals.news"),
        "analysis_pace":          _get("analysis.pace"),
        "analysis_strategy":      _get("analysis.strategy"),
        "analysis_telemetry":     _get("analysis.telemetry"),
        "last_brief_headline":    _get("publish.last"),
    }


def _build_context_for_question(
    question: ResearchQuestion,
    state: StateStore,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Build a focused context dict for a specific specialist question."""
    ctx: dict[str, Any] = {
        "next_race":        snapshot.get("next_race"),
        "weather_forecast": snapshot.get("weather_forecast"),   # always included
    }
    for key in question.context_keys:
        row = state.get(key)
        if row:
            ctx[key] = row.value
    # Always include historical same-track
    if snapshot.get("historical_same_track"):
        ctx["historical_same_track"] = snapshot["historical_same_track"]
    return ctx


def _summarize_findings(findings: list[SpecialistFinding]) -> str:
    """One-line-per-finding summary for cross-department context."""
    lines = []
    for f in findings:
        lines.append(
            f"[{f.department.upper()}] (conf={f.confidence:.2f}) {f.answer_md[:200].replace(chr(10), ' ')}"
        )
    return "\n".join(lines)


def _collect_follow_up_questions(findings: list[SpecialistFinding], budget: int) -> list[str]:
    """Collect valid, deduplicated follow-up questions up to a hard budget."""
    if budget <= 0:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for f in findings:
        if not f.follow_up_allowed:
            continue
        for q in f.follow_up_questions:
            q_norm = (q or "").strip()
            if len(q_norm) < MIN_FOLLOW_UP_QUESTION_LENGTH:
                continue
            if q_norm in seen:
                continue
            seen.add(q_norm)
            out.append(q_norm)
            if len(out) >= budget:
                return out
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Bundle builder — converts SpecialistFindings → InsightBundle
# ─────────────────────────────────────────────────────────────────────────────

def _findings_to_bundle(
    run_id: str,
    agenda: ResearchAgenda,
    findings: list[SpecialistFinding],
    debate: DebateResult | None,
    prediction_finding: SpecialistFinding | None,
) -> InsightBundle:
    """Assemble the final InsightBundle from all specialist outputs."""

    headline = f"{agenda.next_race_name} Research Brief"
    tldr_parts = []

    # Pull key claim from prediction if available
    if prediction_finding:
        tldr_parts.append(prediction_finding.answer_md[:300])
    elif findings:
        top = sorted(findings, key=lambda x: x.confidence, reverse=True)
        tldr_parts.append(top[0].answer_md[:300])

    tldr = " | ".join(tldr_parts) if tldr_parts else "Research complete."

    bundle_findings = []
    all_findings = list(findings)
    if prediction_finding:
        all_findings.append(prediction_finding)

    for f in all_findings:
        bundle_findings.append({
            "id": f.question_id,
            "topic": f.department,
            "summary": _first_sentence(f.answer_md),
            "details_md": f.answer_md,
            "confidence": f.confidence,
            "tags": f.tags,
            "evidence": f.evidence,
        })

    raw_extras: dict[str, Any] = {
        "agenda": {
            "director_notes": agenda.director_notes,
            "key_unknowns": agenda.key_unknowns,
            "question_count": len(agenda.questions),
        }
    }
    if debate:
        raw_extras["debate"] = {
            "challenge_count": len(debate.challenges),
            "consensus_notes": debate.consensus_notes,
            "dissenting_views": debate.dissenting_views,
        }

    # Determine kind
    has_prediction = any(f.department == "prediction" for f in all_findings)
    kind = "race_preview" if has_prediction else "daily_brief"

    return InsightBundle(
        run_id=run_id,
        kind=kind,
        headline=headline,
        tldr=tldr,
        findings=bundle_findings,
        raw=raw_extras,
    )


def _first_sentence(text: str) -> str:
    text = text.strip()
    for sep in (". ", ".\n", "\n"):
        idx = text.find(sep)
        if idx != -1 and idx < 300:
            return text[:idx + 1]
    return text[:200]


# ─────────────────────────────────────────────────────────────────────────────
# Context enrichment jobs (new — populate state keys the Director reads)
# ─────────────────────────────────────────────────────────────────────────────

async def _enrich_recent_results(agent, state: StateStore) -> None:
    """Fetch recent race results and store them."""
    system = (
        "You are a data retrieval agent. You MUST call fastf1_completed_event_schedule "
        "to get the list of completed events, then call fastf1_driver_pace_overview for the "
        "last 3 events to retrieve actual results. Do NOT guess or fabricate any results. "
        "If a tool returns no data, include an empty races list and state why. "
        "Return ONLY JSON: {races: [{event, year, winner, p2, p3, fastest_lap, key_incidents}]}"
    )
    prompt = (
        f"Current time: {_utc_iso()}\n"
        "Step 1: Call fastf1_completed_event_schedule to find the last 3 completed races.\n"
        "Step 2: For each race, call fastf1_driver_pace_overview to get the results.\n"
        "Step 3: Return the structured JSON. Do not fabricate any result."
    )
    res = await run_agent(agent, user_message=prompt, extra_system=system)
    obj = _safe_json(res.get("answer", ""), fallback={"races": []})
    payload = {"results": obj, "updated_at": _utc_iso()}
    valid, reason = validate_enrichment_output("context.recent_results", payload)
    if not valid:
        logger.warning("enrich_recent_results rejected reason=%s", reason)
        payload = {"results": {"races": [], "note": f"validation_failed: {reason}"}, "updated_at": _utc_iso()}
    state.set("context.recent_results", payload)


async def _enrich_standings(agent, state: StateStore) -> None:
    """Fetch current WDC + WCC standings."""
    year = datetime.now(timezone.utc).year
    system = (
        f"You MUST call web_search to get the current {year} F1 WDC and WCC standings. "
        "Do not return the search query as the result — return actual driver/team standings data. "
        "Return ONLY JSON: {wdc: [{pos, driver, team, points, gap_to_leader}], "
        "wcc: [{pos, team, points, gap_to_leader}]}"
    )
    prompt = (
        f"Current time: {_utc_iso()}\n"
        f"Call web_search with query 'F1 {year} championship standings' and extract the actual "
        "standings table from the results. Return structured JSON with wdc and wcc arrays."
    )
    res = await run_agent(agent, user_message=prompt, extra_system=system)
    obj = _safe_json(res.get("answer", ""), fallback={"wdc": [], "wcc": []})
    payload = {"standings": obj, "updated_at": _utc_iso()}
    valid, reason = validate_enrichment_output("context.standings", payload)
    if not valid:
        logger.warning("enrich_standings rejected reason=%s", reason)
        payload = {"standings": {"wdc": [], "wcc": [], "note": f"validation_failed: {reason}"}, "updated_at": _utc_iso()}
    state.set("context.standings", payload)


async def _enrich_historical_same_track(agent, state: StateStore) -> None:
    """Fetch last 2 seasons' results at the same circuit."""
    ctx_row = state.get("context.next_race")
    next_race = (ctx_row.value.get("next_race_openf1") if ctx_row else None) or {}
    circuit = next_race.get("circuit_short_name") or next_race.get("meeting_name") or "unknown circuit"
    year = datetime.now(timezone.utc).year

    system = (
        "You MUST call fastf1_completed_event_schedule for the two previous years and then "
        "fastf1_driver_pace_overview for the matching circuit event. "
        "Return ONLY JSON: {circuit, seasons: [{year, winner, pole, fastest_lap, "
        "winning_strategy, key_observations}]}. "
        "winning_strategy must describe actual tyre compounds used (e.g. 'Soft-Medium one-stop'), "
        "not a generic placeholder. If tool returns no data, include an empty seasons list."
    )
    prompt = (
        f"Current time: {_utc_iso()}\n"
        f"Circuit: {circuit}\n"
        f"Step 1: Call fastf1_completed_event_schedule for {year-2} and {year-1}.\n"
        f"Step 2: Find the {circuit} event in each year's schedule.\n"
        "Step 3: Call fastf1_driver_pace_overview for each to get winner, pole, fastest lap.\n"
        "Step 4: Return structured JSON. Do not use placeholder text for winning_strategy."
    )
    res = await run_agent(agent, user_message=prompt, extra_system=system)
    obj = _safe_json(res.get("answer", ""), fallback={"circuit": circuit, "seasons": []})
    payload = {"history": obj, "updated_at": _utc_iso()}
    valid, reason = validate_enrichment_output("context.historical_same_track", payload)
    if not valid:
        logger.warning("enrich_historical_same_track rejected circuit=%s reason=%s", circuit, reason)
        payload = {"history": {"circuit": circuit, "seasons": [], "note": f"validation_failed: {reason}"}, "updated_at": _utc_iso()}
    state.set("context.historical_same_track", payload)


async def _enrich_telemetry_season_trend(agent, state: StateStore) -> None:
    """Compute high-level pace trend across the current season."""
    year = datetime.now(timezone.utc).year
    system = (
        f"You MUST call fastf1_completed_event_schedule for {year} and then "
        "fastf1_driver_pace_overview for multiple completed races to compute actual pace trends. "
        "Do not fabricate avg_gap_to_p1_ms values — derive them from real lap time data. "
        "Return ONLY JSON: {trends: [{driver, team, trend: improving|declining|stable, "
        "evidence, avg_gap_to_p1_ms}]}. "
        "If no completed races exist yet this season, return {trends: [], note: 'no_completed_races'}."
    )
    prompt = (
        f"Current time: {_utc_iso()}\n"
        f"Step 1: Call fastf1_completed_event_schedule for {year} to get completed races.\n"
        "Step 2: For the top 8 drivers, call fastf1_driver_pace_overview across 3+ events.\n"
        "Step 3: Compute who is improving vs declining based on actual lap time trends.\n"
        "Step 4: Return JSON. evidence must cite specific race names and lap time numbers."
    )
    res = await run_agent(agent, user_message=prompt, extra_system=system)
    obj = _safe_json(res.get("answer", ""), fallback={"trends": []})
    payload = {"season_trend": obj, "updated_at": _utc_iso()}
    valid, reason = validate_enrichment_output("context.telemetry_season_trend", payload)
    if not valid:
        logger.warning("enrich_telemetry_season_trend rejected reason=%s", reason)
        payload = {"season_trend": {"trends": [], "note": f"validation_failed: {reason}"}, "updated_at": _utc_iso()}
    state.set("context.telemetry_season_trend", payload)


# ─────────────────────────────────────────────────────────────────────────────
# Core research flow
# ─────────────────────────────────────────────────────────────────────────────

async def _run_specialist(
    agent,
    question: ResearchQuestion,
    context: dict[str, Any],
    prior_findings_summary: str,
) -> SpecialistFinding:
    """
    Run one specialist agent on one question.
    The agent may iterate up to MAX_EXPLORATION_ROUNDS, each time potentially
    calling more tools and refining its answer.
    """
    system = DEPT_SYSTEMS.get(question.department, DEPT_SYSTEMS["general"])
    prompt = build_specialist_prompt(question, context, prior_findings_summary)
    timeout_seconds = MAX_SPECIALIST_TIMEOUT_SECONDS
    if timeout_seconds < 1:
        logger.warning(
            "invalid_specialist_timeout configured=%d using=1",
            timeout_seconds,
        )
        timeout_seconds = 1

    exploration_depth = 0
    last_finding: SpecialistFinding | None = None

    for round_num in range(MAX_EXPLORATION_ROUNDS):
        exploration_depth = round_num + 1

        if round_num > 0 and last_finding:
            # Give the agent its previous answer and ask if it wants to go deeper
            refine_prompt = (
                f"PREVIOUS ANSWER (round {round_num}):\n"
                f"{last_finding.answer_md[:1000]}\n\n"
                f"Follow-up questions you raised:\n"
                + "\n".join(f"  - {q}" for q in last_finding.follow_up_questions)
                + "\n\nNow investigate those follow-up questions using more tool calls. "
                "Return your UPDATED complete JSON answer."
            )
            prompt = refine_prompt

        try:
            res = await asyncio.wait_for(
                run_agent(agent, user_message=prompt, extra_system=system),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "specialist_timeout question_id=%s dept=%s round=%d timeout_s=%d",
                question.id,
                question.department,
                exploration_depth,
                timeout_seconds,
            )
            timeout_msg = (
                "Specialist timed out before completing this round. "
                "Result may be incomplete."
            )
            if last_finding:
                last_finding.answer_md = f"{last_finding.answer_md}\n\n{timeout_msg}"
                break
            return SpecialistFinding(
                question_id=question.id,
                department=question.department,
                question=question.question,
                answer_md=timeout_msg,
                confidence=0.0,
                tags=[question.department, "timeout"],
                evidence=[],
                follow_up_questions=[],
                exploration_depth=exploration_depth,
                raw_tool_calls=[],
            )
        finding = parse_specialist_finding(question, res.get("answer", ""), exploration_depth)
        last_finding = finding

        # Stop early if no follow-ups requested or confidence is high
        if not finding.follow_up_questions or finding.confidence >= 0.85:
            break

    return last_finding  # type: ignore[return-value]


async def _run_debate_round(
    agent,
    findings: list[SpecialistFinding],
) -> DebateResult:
    """
    Each specialist challenges one other specialist's finding.
    Then the challenged specialist responds (possibly with more tool calls).
    """
    if not findings or DEBATE_ROUNDS == 0:
        return DebateResult(findings=findings, challenges=[], consensus_notes="Debate skipped.", dissenting_views=[])

    challenges: list[DebateChallenge] = []
    all_summary = _summarize_findings(findings)

    # Each dept challenges the next dept's finding (round-robin)
    depts = [f.department for f in findings]
    for i, finding in enumerate(findings):
        challenger_dept = depts[(i + 1) % len(depts)]
        system = DEPT_SYSTEMS.get(challenger_dept, DEPT_SYSTEMS["general"])
        debate_prompt = build_debate_prompt(finding, challenger_dept, all_summary)

        res = await run_agent(agent, user_message=debate_prompt, extra_system=system)
        challenge = parse_debate_challenge(res.get("answer", ""), challenger_dept, finding.question_id)
        if not challenge:
            continue

        # Skip if reviewer says finding is solid
        if "FINDING IS SOLID" in challenge.challenge.upper():
            continue

        # Run resolution — original specialist responds
        orig_system = DEPT_SYSTEMS.get(finding.department, DEPT_SYSTEMS["general"])
        resolution_prompt = build_resolution_prompt(finding, challenge.challenge, "")
        res2 = await run_agent(agent, user_message=resolution_prompt, extra_system=orig_system)
        resolution = parse_resolution(res2.get("answer", ""))

        # Update finding confidence based on resolution
        updated_conf = float(resolution.get("updated_confidence") or finding.confidence)
        finding.confidence = max(0.0, min(1.0, updated_conf))
        if resolution.get("answer_update"):
            finding.answer_md += f"\n\n**Post-debate update:** {resolution['answer_update']}"

        challenge.resolution = str(resolution.get("resolution") or "")
        challenges.append(challenge)

    # Identify consensus vs dissent
    low_conf = [f for f in findings if f.confidence < 0.5]
    dissenting = [f"{f.department}: {_first_sentence(f.answer_md)}" for f in low_conf]

    return DebateResult(
        findings=findings,
        challenges=challenges,
        consensus_notes=f"{len(challenges)} challenges raised and resolved.",
        dissenting_views=dissenting,
    )


async def _run_prediction_synthesis(
    agent,
    findings: list[SpecialistFinding],
    agenda: ResearchAgenda,
    state: StateStore,
) -> SpecialistFinding:
    """
    Final synthesis step — prediction specialist reads ALL findings and
    produces structured race predictions.
    """
    # Build a synthetic question for prediction
    pred_question = ResearchQuestion(
        id="synthesis-prediction",
        department="prediction",
        question=(
            f"Given all research findings for {agenda.next_race_name}, "
            "produce race winner probabilities, podium prediction, qualifying top-5, "
            "tyre strategies per top team, wildcard scenarios, and championship impact."
        ),
        priority=1,
        context_keys=[],
    )

    snapshot = _build_knowledge_snapshot(state)
    context = _build_context_for_question(pred_question, state, snapshot)
    prior_summary = _summarize_findings(findings)

    return await _run_specialist(agent, pred_question, context, prior_summary)


# ─────────────────────────────────────────────────────────────────────────────
# Main corporation class
# ─────────────────────────────────────────────────────────────────────────────

class F1ResearchCorporation:
    """
    Autonomous multi-department F1 research system.

    Research cycle (v2):
      1. Enrich context (recent results, standings, same-track history, season trends)
      2. Director generates a fresh ResearchAgenda
      3. Specialist agents investigate questions in parallel (with follow-ups)
      4. Debate coordinator cross-checks findings
      5. Prediction synthesizer produces probabilistic race outlook
      6. Publisher assembles InsightBundle
      7. Verifier audits and publishes
    """

    def __init__(
        self,
        *,
        settings: Settings,
        kb: JsonlKnowledgeBase,
        scheduler: JobScheduler,
        store: InsightStore,
    ):
        self.settings = settings
        self.kb = kb
        self.scheduler = scheduler
        self.store = store

        self.enabled = os.getenv("AUTONOMOUS_ENABLED", "0") == "1"
        self.owner = os.getenv("AUTONOMOUS_WORKER_ID", uuid.uuid4().hex[:8])
        self.lease_seconds = int(os.getenv("AUTONOMOUS_LEASE_SECONDS", "300"))
        self.idle_sleep = float(os.getenv("AUTONOMOUS_IDLE_SLEEP_SECONDS", "2"))

        state_path = os.getenv("AUTONOMOUS_STATE_DB", "./data/autonomous_state.sqlite")
        self.state = StateStore(state_path)
        artifacts_root = os.getenv("AUTONOMOUS_ARTIFACTS_DIR", "./data/artifacts")
        self.artifacts = ArtifactStore(artifacts_root)

        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._agent = None

        self.scheduler.seed_periodic_jobs(DEFAULT_JOBS)

    # ── lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                self._task.cancel()

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "running": bool(self._task and not self._task.done()),
            "owner": self.owner,
            "lease_seconds": self.lease_seconds,
            "last_job": getattr(self, "_last_job", None),
            "last_job_at": getattr(self, "_last_job_at", None),
        }

    async def _ensure_agent(self):
        if self._agent is None:
            self._agent = build_agent(self.settings, self.kb)
        return self._agent

    # ── job loop ────────────────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        if not self.enabled:
            logger.info("corp_disabled")
            return

        logger.info("corp_start owner=%s", self.owner)
        while not self._stop.is_set():
            due = self.scheduler.lease_next(owner=self.owner, lease_seconds=self.lease_seconds)
            if not due:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.idle_sleep)
                except asyncio.TimeoutError:
                    pass
                continue

            self._last_job = due.job_type.value
            self._last_job_at = _utc_iso()

            t0 = time.time()
            try:
                await self._execute_job(due.job_type)
                self.scheduler.mark_success(due.id)
                _re_enq_seconds = _next_interval_seconds(due.job_type)
                if _re_enq_seconds:
                    when = datetime.fromtimestamp(
                        time.time() + _re_enq_seconds, tz=timezone.utc
                    ).isoformat()
                    self.scheduler.enqueue(due.job_type, scheduled_at=when)
            except Exception as e:
                logger.exception("corp_job_failed job=%s err=%s", due.job_type.value, e)
                backoff = min(3600, 60 * (2 ** min(6, due.attempts)))
                self.scheduler.mark_failure(due.id, error=str(e), backoff_seconds=backoff)
            finally:
                logger.info(
                    "corp_job_done job=%s duration_ms=%s",
                    due.job_type.value,
                    int((time.time() - t0) * 1000),
                )

        logger.info("corp_stop")

    # ── job dispatch ────────────────────────────────────────────────────────

    async def _execute_job(self, job_type: JobType) -> None:
        dispatch = {
            JobType.next_race_context:   self._job_next_race_context,
            JobType.weather_update:      self._job_weather_update,
            JobType.ingest_news:         self._job_ingest_news,
            JobType.analyze_pace:        lambda: self._job_analysis(JobType.analyze_pace),
            JobType.analyze_strategy:    lambda: self._job_analysis(JobType.analyze_strategy),
            JobType.analyze_telemetry:   lambda: self._job_analysis(JobType.analyze_telemetry),
            JobType.verify_bundle:       self._job_verify_bundle,
            JobType.daily_brief:         self._job_full_research_cycle,
            JobType.telemetry_watch:     self._job_telemetry_watch,
        }
        handler = dispatch.get(job_type)
        if handler:
            await handler()
        else:
            logger.warning("unknown_job job=%s", job_type.value)

    # ── context jobs (largely unchanged, now feed Director) ─────────────────

    async def _job_next_race_context(self) -> None:
        year = int(os.getenv("F1_CONTEXT_YEAR", str(datetime.now(timezone.utc).year)))
        next_race = compute_next_race_openf1(year=year)
        payload = {"next_race_openf1": next_race, "updated_at": _utc_iso()}
        self.state.set("context.next_race", payload)
        persist_department_snapshot(self.kb, "context.next_race", payload)

    async def _job_weather_update(self) -> None:
        ctx = self.state.get("context.next_race")
        next_race = (ctx.value.get("next_race_openf1") if ctx else None)
        weather = summarize_weather_openf1(next_race)
        payload = {"weather_openf1": weather, "updated_at": _utc_iso()}
        self.state.set("context.weather", payload)
        persist_department_snapshot(self.kb, "context.weather", payload)

    async def _job_ingest_news(self) -> None:
        if self._is_demo_mode():
            self._store_demo_news()
            return
        agent = await self._ensure_agent()
        year = datetime.now(timezone.utc).year
        system = (
            "You are the News Signals Department.\n"
            "You MUST call web_search at least 3 times with different queries, then call "
            "scrape_webpage on the most promising results to get full article text.\n"
            "CRITICAL: Every item's URL must be a real URL returned by web_search or scrape_webpage. "
            "NEVER use example.com or placeholder URLs. "
            "NEVER invent headlines, injuries, penalties, or upgrades that were not in a search result.\n"
            "Return ONLY valid JSON: {items: [{id, title, summary, url, credibility, tags[]}]}\n"
            "Focus on: technical upgrades, penalties, injuries, regulation changes, "
            "driver contract pressure, team orders."
        )
        prompt = (
            f"Time now (UTC): {_utc_iso()}\n"
            f"Step 1: Call web_search('F1 {year} latest news')\n"
            f"Step 2: Call web_search('Formula 1 {year} technical upgrades penalties')\n"
            f"Step 3: Call web_search('F1 driver news {year} contract injury')\n"
            "Step 4: Call scrape_webpage on the 3-4 most promising URLs from those results.\n"
            "Step 5: Return 8-12 items using ONLY information from those actual search results. "
            "Every url field must be a real URL from the search results."
        )
        res = await run_agent(agent, user_message=prompt, extra_system=system)
        obj = _safe_json(res.get("answer", ""), fallback={"items": []})

        # Strip any items with fabricated/placeholder URLs
        real_items = [
            item for item in (obj.get("items") or [])
            if isinstance(item.get("url"), str)
            and item["url"]
            and "example.com" not in item["url"]
            and item["url"].startswith("http")
        ]
        if len(real_items) < len(obj.get("items") or []):
            n_stripped = len((obj.get("items") or [])) - len(real_items)
            logger.warning("news_url_filter stripped %d items with fake/missing URLs", n_stripped)

        payload = {"news": {"items": real_items}, "updated_at": _utc_iso()}
        self.state.set("signals.news", payload)
        persist_department_snapshot(self.kb, "signals.news", payload)

    async def _job_telemetry_watch(self) -> None:
        payload = {"ok": True, "note": "telemetry_watch scheduled via full cycle", "updated_at": _utc_iso()}
        self.state.set("signals.telemetry_watch", payload)

    async def _job_analysis(self, job_type: JobType) -> None:
        """Legacy single-department analysis — still works, feeds state for Director."""
        if self._is_demo_mode():
            key = {
                JobType.analyze_pace:      "analysis.pace",
                JobType.analyze_strategy:  "analysis.strategy",
                JobType.analyze_telemetry: "analysis.telemetry",
            }[job_type]
            self.state.set(key, {"note": "demo mode", "job": job_type.value, "updated_at": _utc_iso()})
            return

        agent = await self._ensure_agent()
        ctx_row = self.state.get("context.next_race")
        ctx_val = ctx_row.value if ctx_row else {}
        weather_row = self.state.get("context.weather")
        weather_val = weather_row.value if weather_row else {}
        history_row = self.state.get("context.historical_same_track")
        history_val = history_row.value if history_row else {}

        if job_type == JobType.analyze_pace:
            system = DEPT_SYSTEMS["pace"]
            prompt = (
                f"Context: {json.dumps(ctx_val)}\nWeather: {json.dumps(weather_val)}\n"
                f"Historical same track: {json.dumps(history_val)}\n"
                "Perform a full pace analysis for this race weekend. "
                "Compare current season to same circuit last season."
            )
            res = await run_agent(agent, user_message=prompt, extra_system=system)
            obj = _safe_json(res.get("answer", ""), fallback={"summary": ""})
            self.state.set("analysis.pace", {"pace": obj, "updated_at": _utc_iso()})
            self.artifacts.put_json("tables/pace.json", obj)

        elif job_type == JobType.analyze_strategy:
            system = DEPT_SYSTEMS["strategy"]
            prompt = (
                f"Context: {json.dumps(ctx_val)}\nWeather: {json.dumps(weather_val)}\n"
                f"Historical same track: {json.dumps(history_val)}\n"
                "Produce a full strategy landscape analysis. Include scenario trees."
            )
            res = await run_agent(agent, user_message=prompt, extra_system=system)
            obj = _safe_json(res.get("answer", ""), fallback={"summary": ""})
            self.state.set("analysis.strategy", {"strategy": obj, "updated_at": _utc_iso()})
            self.artifacts.put_json("tables/strategy_deg.json", obj)

        elif job_type == JobType.analyze_telemetry:
            system = DEPT_SYSTEMS["telemetry"]
            prompt = (
                f"Context: {json.dumps(ctx_val)}\n"
                f"Historical same track: {json.dumps(history_val)}\n"
                "Find non-obvious telemetry patterns for this race weekend."
            )
            res = await run_agent(agent, user_message=prompt, extra_system=system)
            obj = _safe_json(res.get("answer", ""), fallback={"summary": ""})
            self.state.set("analysis.telemetry", {"telemetry": obj, "updated_at": _utc_iso()})
            self.artifacts.put_json("tables/telemetry_minisectors.json", obj)

    # ── CORE: full research cycle (replaces _job_publish_daily_brief) ───────

    async def _job_full_research_cycle(self) -> None:
        """
        The main v2 research cycle:
          1. Enrich context (recent results, standings, history, season trend)
          2. Director generates agenda
          3. Specialists investigate in parallel
          4. Debate cross-check
          5. Prediction synthesis
          6. Assemble candidate bundle
          7. Queue verification
        """
        run_id = uuid.uuid4().hex[:10]
        logger.info("research_cycle_start run_id=%s", run_id)

        if self._is_demo_mode():
            await self._publish_demo_bundle(run_id)
            return

        agent = await self._ensure_agent()

        # ── Step 1: Enrich context ───────────────────────────────────────
        logger.info("research_cycle_enrich run_id=%s", run_id)
        enrich_tasks = [
            _enrich_recent_results(agent, self.state),
            _enrich_standings(agent, self.state),
            _enrich_historical_same_track(agent, self.state),
            _enrich_telemetry_season_trend(agent, self.state),
        ]
        enrich_names = [
            "recent_results",
            "standings",
            "historical_same_track",
            "telemetry_season_trend",
        ]
        enrich_results = await asyncio.gather(*enrich_tasks, return_exceptions=True)
        for name, result in zip(enrich_names, enrich_results):
            if isinstance(result, Exception):
                logger.warning(
                    "research_cycle_enrich_failed run_id=%s task=%s err=%s",
                    run_id,
                    name,
                    str(result)[:300],
                )

        # ── Step 2: Director generates agenda ───────────────────────────
        logger.info("research_cycle_director run_id=%s", run_id)
        snapshot = _build_knowledge_snapshot(self.state)
        prior_headlines = self._get_prior_headlines()
        director_prompt = build_director_prompt(snapshot, prior_headlines)
        director_res = await run_agent(
            agent,
            user_message=director_prompt,
            extra_system=_DIRECTOR_SYSTEM,
        )
        agenda = parse_agenda(run_id, director_res.get("answer", ""))
        logger.info(
            "research_cycle_agenda run_id=%s questions=%d race=%s",
            run_id, len(agenda.questions), agenda.next_race_name,
        )
        self.state.set("research.last_agenda", {
            "run_id": run_id,
            "next_race": agenda.next_race_name,
            "question_count": len(agenda.questions),
            "director_notes": agenda.director_notes,
            "key_unknowns": agenda.key_unknowns,
            "updated_at": _utc_iso(),
        })

        # ── Step 3: Parallel specialist investigation ────────────────────
        logger.info("research_cycle_specialists run_id=%s", run_id)
        # Sort by priority; exclude prediction dept (handled in step 5)
        research_questions = [
            q for q in agenda.questions
            if q.department != "prediction"
        ][:12]  # cap total questions

        # Add any Director-requested follow-ups (up to MAX_FOLLOW_UP_QUESTIONS)
        follow_up_budget = MAX_FOLLOW_UP_QUESTIONS

        sem = asyncio.Semaphore(SPECIALIST_CONCURRENCY)
        findings: list[SpecialistFinding] = []

        async def _run_with_sem(q: ResearchQuestion, prior_summary: str) -> SpecialistFinding:
            async with sem:
                ctx = _build_context_for_question(q, self.state, snapshot)
                return await _run_specialist(agent, q, ctx, prior_summary)

        # Run high-priority questions first (priority 1-2), then the rest
        high_priority = [q for q in research_questions if q.priority <= 2]
        low_priority  = [q for q in research_questions if q.priority > 2]

        # Phase A: high-priority in parallel
        high_tasks = [_run_with_sem(q, "") for q in high_priority]
        high_findings = await asyncio.gather(*high_tasks, return_exceptions=True)
        for f in high_findings:
            if isinstance(f, SpecialistFinding):
                findings.append(f)

        # Phase B: low-priority, with access to high-priority findings
        prior_summary = _summarize_findings(findings)
        low_tasks = [_run_with_sem(q, prior_summary) for q in low_priority]
        low_findings = await asyncio.gather(*low_tasks, return_exceptions=True)
        for f in low_findings:
            if isinstance(f, SpecialistFinding):
                findings.append(f)

        # Phase C: follow-up questions from specialists
        all_follow_ups = _collect_follow_up_questions(findings, follow_up_budget)

        if all_follow_ups:
            fu_summary = _summarize_findings(findings)
            fu_tasks = []
            for i, fq_text in enumerate(all_follow_ups):
                # Infer department from context
                dept = _infer_dept_from_question(fq_text)
                fq = ResearchQuestion(
                    id=f"followup-{run_id}-{i+1}",
                    department=dept,
                    question=fq_text,
                    priority=3,
                    context_keys=[],
                )
                fu_tasks.append(_run_with_sem(fq, fu_summary))
            fu_findings = await asyncio.gather(*fu_tasks, return_exceptions=True)
            for f in fu_findings:
                if isinstance(f, SpecialistFinding):
                    findings.append(f)

        logger.info("research_cycle_findings_done run_id=%s count=%d", run_id, len(findings))

        # ── Step 4: Debate ───────────────────────────────────────────────
        logger.info("research_cycle_debate run_id=%s", run_id)
        debate = await _run_debate_round(agent, findings)

        # ── Step 5: Prediction synthesis ────────────────────────────────
        logger.info("research_cycle_prediction run_id=%s", run_id)
        prediction_finding = await _run_prediction_synthesis(agent, findings, agenda, self.state)

        # Save prediction artifact
        self.artifacts.put_json(f"predictions/{run_id}.json", {
            "answer_md": prediction_finding.answer_md,
            "confidence": prediction_finding.confidence,
            "evidence": prediction_finding.evidence,
        })

        # ── Step 6: Assemble candidate bundle ───────────────────────────
        logger.info("research_cycle_assemble run_id=%s", run_id)
        bundle = _findings_to_bundle(run_id, agenda, findings, debate, prediction_finding)

        self.state.set("publish.candidate", {
            "run_id": run_id,
            "bundle": bundle.model_dump(mode="json"),
            "updated_at": _utc_iso(),
        })
        persist_department_snapshot(self.kb, "publish.candidate", {
            "headline": bundle.headline,
            "run_id": run_id,
            "finding_count": len(findings),
        })

        # ── Step 7: Queue verification ───────────────────────────────────
        self.scheduler.enqueue(JobType.verify_bundle)
        logger.info("research_cycle_done run_id=%s", run_id)

    # ── Verify/publish (enhanced) ────────────────────────────────────────────

    async def _job_verify_bundle(self) -> None:
        row = self.state.get("publish.candidate")
        if not row:
            return
        bundle = row.value.get("bundle")
        if not bundle:
            return

        candidate_run_id = row.value.get("run_id")
        if candidate_run_id and isinstance(bundle, dict):
            if bundle.get("run_id") and bundle.get("run_id") != candidate_run_id:
                logger.warning("verify_skipped_stale_candidate")
                return

        if self._is_demo_mode():
            verdict = {"pass": True, "issues": [], "fixes": [], "mode": "demo_no_llm"}
            self.state.set("publish.verdict", {"verdict": verdict, "updated_at": _utc_iso()})
            ib = InsightBundle.model_validate(bundle)
            self.store.append(ib)
            self.state.set("publish.last", {
                "run_id": ib.run_id,
                "headline": ib.headline,
                "updated_at": _utc_iso(),
            })
            return

        agent = await self._ensure_agent()
        system = (
            "You are the Skeptic/Verification Department.\n"
            "Audit this research bundle for:\n"
            "  1. Evidence quality — every finding must cite data or a credible source\n"
            "  2. Confidence calibration — does stated confidence match evidence strength?\n"
            "  3. Prediction specificity — are probabilities stated, not vague?\n"
            "  4. Internal consistency — do findings contradict each other without explanation?\n"
            "  5. Novelty — does this avoid rehashing obvious or generic F1 commentary?\n"
            "Return strict JSON: {pass: bool, score: 0-10, issues: [], fixes: [], "
            "prediction_quality: 'excellent|good|weak|missing'}\n"
        )
        prompt = (
            f"Bundle to verify:\n{json.dumps(bundle, ensure_ascii=False)}\n\n"
            "Be rigorous. A bundle passes only if score >= 6 AND every prediction "
            "has an explicit probability or quantitative backing."
        )
        res = await run_agent(agent, user_message=prompt, extra_system=system)
        verdict = _safe_json(
            res.get("answer", ""),
            fallback={"pass": False, "score": 0, "issues": ["unparseable_verdict"], "fixes": []},
        )
        self.state.set("publish.verdict", {"verdict": verdict, "updated_at": _utc_iso()})

        if verdict.get("pass") is True:
            ib = InsightBundle.model_validate(bundle)
            self.store.append(ib)
            self.state.set("publish.last", {
                "run_id": ib.run_id,
                "headline": ib.headline,
                "updated_at": _utc_iso(),
            })
        else:
            persist_department_snapshot(self.kb, "publish.verdict", verdict)
            logger.warning(
                "bundle_rejected score=%s issues=%s",
                verdict.get("score"),
                verdict.get("issues"),
            )

    # ── Demo / run-once helpers ──────────────────────────────────────────────

    async def run_flow_once(self, *, demo: bool = True) -> dict[str, Any]:
        if demo:
            os.environ.setdefault("CORP_DEMO_MODE", "1")
        else:
            os.environ["CORP_DEMO_MODE"] = "0"

        trace: dict[str, Any] = {"started_at": _utc_iso(), "steps": [], "demo_mode": demo}

        async def _step(name: str, fn) -> bool:
            t0 = time.time()
            try:
                await fn()
                trace["steps"].append({"step": name, "ok": True, "duration_ms": int((time.time() - t0) * 1000)})
                return True
            except Exception as e:
                trace["steps"].append({
                    "step": name, "ok": False,
                    "duration_ms": int((time.time() - t0) * 1000), "error": str(e),
                })
                return False

        await _step("next_race_context",   self._job_next_race_context)
        await _step("weather_update",      self._job_weather_update)
        await _step("ingest_news",         self._job_ingest_news)
        publish_ok = await _step("full_research_cycle", self._job_full_research_cycle)
        if publish_ok:
            await _step("verify_bundle", self._job_verify_bundle)
        else:
            trace["steps"].append({"step": "verify_bundle", "ok": False, "error": "skipped"})

        trace["finished_at"] = _utc_iso()
        trace["state_keys"] = {k: bool(self.state.get(k)) for k in [
            "context.next_race", "context.weather", "context.recent_results",
            "context.standings", "context.historical_same_track",
            "context.telemetry_season_trend", "signals.news",
            "research.last_agenda", "publish.candidate",
            "publish.verdict", "publish.last",
        ]}
        return trace

    async def run_verify_once_if_candidate_exists(self) -> bool:
        row = self.state.get("publish.candidate")
        if not row or not row.value.get("bundle"):
            return False
        await self._job_verify_bundle()
        return True

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _is_demo_mode(self) -> bool:
        if os.getenv("CORP_DEMO_MODE", "0") == "1":
            return True
        provider = (os.getenv("LLM_PROVIDER", "openrouter") or "openrouter").lower()
        if provider == "openrouter" and not os.getenv("OPENROUTER_API_KEY"):
            return True
        if provider == "groq" and not os.getenv("GROQ_API_KEY"):
            return True
        return False

    def _get_prior_headlines(self) -> list[str]:
        rows = []
        for key in ["publish.last"]:
            row = self.state.get(key)
            if row and row.value.get("headline"):
                rows.append(row.value["headline"])
        return rows

    def _store_demo_news(self) -> None:
        payload = {
            "news": {"items": [{
                "id": "demo-1",
                "title": "Demo mode: LLM API key not set",
                "summary": "Set OPENROUTER_API_KEY or GROQ_API_KEY to enable live research.",
                "url": "", "credibility": 0.2, "tags": ["demo"],
            }]},
            "updated_at": _utc_iso(),
            "mode": "demo_no_llm",
        }
        self.state.set("signals.news", payload)
        persist_department_snapshot(self.kb, "signals.news", payload)

    async def _publish_demo_bundle(self, run_id: str) -> None:
        """Deterministic demo bundle when LLM key is absent."""
        snapshots = {
            k: (self.state.get(k).value if self.state.get(k) else {})
            for k in ["context.next_race", "context.weather", "signals.news"]
        }
        demo = InsightBundle(
            run_id=run_id,
            kind="race_preview",
            headline="Demo Race Preview (LLM disabled)",
            tldr="Set OPENROUTER_API_KEY or GROQ_API_KEY to enable the full research pipeline.",
            findings=[
                {
                    "id": "demo-context",
                    "topic": "context",
                    "summary": "Next race context loaded from OpenF1.",
                    "details_md": "Context enrichment ran successfully. Enable LLM for full analysis.",
                    "confidence": 0.8, "tags": ["context", "demo"],
                    "evidence": [{"source_type": "openf1", "source_id": "state:context.next_race", "title": None}],
                },
                {
                    "id": "demo-prediction",
                    "topic": "prediction",
                    "summary": "Predictions unavailable in demo mode.",
                    "details_md": "Race winner probabilities, tyre strategies, and qualifying predictions require the LLM pipeline.",
                    "confidence": 0.0, "tags": ["prediction", "demo"],
                    "evidence": [],
                },
            ],
            raw={"snapshots": snapshots, "mode": "demo_no_llm"},
        )
        self.state.set("publish.candidate", {
            "run_id": run_id,
            "bundle": demo.model_dump(mode="json"),
            "updated_at": _utc_iso(),
        })
        self.scheduler.enqueue(JobType.verify_bundle)


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────

def _infer_dept_from_question(text: str) -> str:
    text_lower = text.lower()
    if any(w in text_lower for w in ["tyre", "tire", "strategy", "stint", "undercut", "pit"]):
        return "strategy"
    if any(w in text_lower for w in ["telemetry", "sector", "braking", "throttle", "ers"]):
        return "telemetry"
    if any(w in text_lower for w in ["weather", "rain", "temperature", "forecast", "wind"]):
        return "weather"
    if any(w in text_lower for w in ["news", "upgrade", "penalty", "injury", "contract"]):
        return "news"
    if any(w in text_lower for w in ["predict", "winner", "podium", "probability", "championship"]):
        return "prediction"
    return "pace"


def _next_interval_seconds(job_type: JobType) -> int | None:
    for spec in DEFAULT_JOBS:
        if spec.job_type == job_type:
            return spec.interval_seconds
    return None
