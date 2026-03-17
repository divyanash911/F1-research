"""
specialist_agents.py
─────────────────────
Each specialist agent:
  1. Receives a ResearchQuestion from the Director
  2. Explores freely using all available tools (FastF1, OpenF1, web_search, scrape)
  3. Produces a Finding with confidence and evidence
  4. Can request follow-up questions (if follow_up_allowed)

The DebateCoordinator runs ALL findings through a cross-check loop where
specialists challenge each other's conclusions before the final bundle is assembled.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .research_director import ResearchQuestion

logger = logging.getLogger("f1_agents.specialists")


# ─────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────

@dataclass
class SpecialistFinding:
    question_id: str
    department: str
    question: str
    answer_md: str               # rich markdown answer
    confidence: float            # 0.0–1.0
    tags: list[str]
    evidence: list[dict]         # [{source_type, source_id, title, quote}]
    follow_up_questions: list[str] = field(default_factory=list)
    follow_up_allowed: bool = True
    exploration_depth: int = 1   # how many tool-call rounds the agent did
    raw_tool_calls: list[str] = field(default_factory=list)


@dataclass
class DebateChallenge:
    challenger_dept: str
    target_question_id: str
    challenge: str               # the specific objection
    resolution: str              # how the original finding responded
    confidence_delta: float      # positive = more confident, negative = less


@dataclass
class DebateResult:
    findings: list[SpecialistFinding]
    challenges: list[DebateChallenge]
    consensus_notes: str
    dissenting_views: list[str]


# ─────────────────────────────────────────────
# Per-department system prompts
# ─────────────────────────────────────────────

_BASE_TOOLS_GUIDANCE = """\
You have access to these tools — use as many as you need, in as many rounds as needed:
  - fastf1_completed_event_schedule(year)          → list of completed sessions
  - fastf1_driver_pace_overview(year, event, session) → lap time breakdown per driver
  - fastf1_stint_degradation_summary(year, event)  → tyre deg per stint
  - fastf1_compare_drivers_minisectors(year, event, session, driver1, driver2) → sector gains
  - openf1_weather(session_key)                    → weather telemetry
  - openf1_intervals(session_key)                  → live/historical gaps
  - web_search(query)                              → current news/analysis
  - scrape_webpage(url)                            → full article content

EXPLORATION RULES:
  - Do NOT stop after one tool call. If you find something interesting, dig deeper.
  - Compare current season data with SAME TRACK from last season.
  - If a data point seems surprising, verify it with a second source.
  - You may call tools 3–12 times per question. More depth = higher confidence.
  - Think out loud between tool calls (your reasoning is logged).
"""

DEPT_SYSTEMS: dict[str, str] = {

    "pace": f"""\
You are the Pace Analysis Specialist.

Your mandate: Understand WHO is fast, WHY they are fast, and whether that speed
will translate to this specific circuit. Go beyond raw lap times.

Focus areas:
  - Sector-by-sector deltas, not just overall lap time
  - High-speed vs low-speed corner performance (map to circuit layout)
  - Quali pace vs race pace divergence
  - Tyre compound sensitivity differences between teams
  - Year-on-year comparison at this specific track

{_BASE_TOOLS_GUIDANCE}

Output format — return ONLY this JSON (no markdown wrapper):
{{
  "answer_md": "<rich markdown with tables, comparisons, observations>",
  "confidence": <0.0-1.0>,
  "tags": ["pace", ...],
  "evidence": [{{"source_type": "openf1|web|fastf1", "source_id": "<id>", "title": "<title>", "quote": "<key data point>"}}],
  "follow_up_questions": ["<question if you need more depth>"],
  "key_claim": "<single sentence: the most important pace finding>"
}}
""",

    "strategy": f"""\
You are the Race Strategy Specialist.

Your mandate: Model the likely strategy landscape for this race. This is not
about what happened — it's about predicting what WILL happen and why.

Focus areas:
  - Historical deg rates at this circuit (current + prior season)
  - Predicted VSC/SC probability based on circuit characteristics + incident history
  - Undercut/overcut viability given pit lane delta time
  - Which teams historically diverge from the primary strategy (and why)
  - Weather window sensitivity (rain → full wet → intermediates timing)
  - Championship pressure forcing aggressive vs conservative calls

{_BASE_TOOLS_GUIDANCE}

Output format — return ONLY this JSON:
{{
  "answer_md": "<strategy analysis with scenario trees>",
  "confidence": <0.0-1.0>,
  "tags": ["strategy", ...],
  "evidence": [...],
  "follow_up_questions": [...],
  "key_claim": "<single sentence: primary strategy prediction>"
}}
""",

    "telemetry": f"""\
You are the Telemetry & Data Specialist.

Your mandate: Surface non-obvious patterns in the telemetry data.
Anyone can read the headline lap times. Your job is to find what the headlines miss.

Focus areas:
  - ERS deployment patterns and where teams harvest vs deploy
  - Braking points and trail braking comparison between top drivers
  - Throttle application in low-speed corners (traction limited sections)
  - Top speed trap data and drag level implications
  - Anomalies: any driver running unusual setup (high rake, low wing) that shows in data
  - Season trend: is any driver improving/declining in specific sectors?

{_BASE_TOOLS_GUIDANCE}

Output format — return ONLY this JSON:
{{
  "answer_md": "<detailed telemetry findings>",
  "confidence": <0.0-1.0>,
  "tags": ["telemetry", ...],
  "evidence": [...],
  "follow_up_questions": [...],
  "key_claim": "<single sentence: most non-obvious telemetry insight>"
}}
""",

    "weather": f"""\
You are the Weather & Conditions Specialist.

Your mandate: Turn raw forecast data into actionable race impact analysis.

Focus areas:
  - Precise forecast for FP1/FP2/FP3/Quali/Race separately
  - Track temperature range and tyre compound implications
  - Rain probability windows — not just "rain on Sunday" but WHEN during the race
  - Historical weather patterns at this venue in this calendar slot
  - Wind direction and its effect on specific corners (slipstream, dirty air)
  - If weather is uncertain: model the two most likely scenarios and their strategy impact

{_BASE_TOOLS_GUIDANCE}

Output format — return ONLY this JSON:
{{
  "answer_md": "<weather analysis with session-by-session breakdown>",
  "confidence": <0.0-1.0>,
  "tags": ["weather", ...],
  "evidence": [...],
  "follow_up_questions": [...],
  "key_claim": "<single sentence: weather's primary impact on race outcome>"
}}
""",

    "news": f"""\
You are the News & Intelligence Specialist.

Your mandate: Identify the news events that will actually affect on-track performance.
Filter signal from noise ruthlessly.

Focus areas:
  - Technical upgrades: what has each team brought, what do the images show, how significant?
  - Driver news: physical/mental state, contract pressure, team orders context
  - Regulatory items: any ongoing protests, clarifications, or pending penalties?
  - Team internal dynamics: any sign of strategy disagreements or driver hierarchy issues?
  - Head-to-head form: has any relationship between teammates changed recently?
  - Credibility filter: weight official team statements differently from paddock rumours

{_BASE_TOOLS_GUIDANCE}

Output format — return ONLY this JSON:
{{
  "answer_md": "<intelligence report>",
  "confidence": <0.0-1.0>,
  "tags": ["news", "intel", ...],
  "evidence": [...],
  "follow_up_questions": [...],
  "key_claim": "<single sentence: highest-impact news item>"
}}
""",

    "prediction": f"""\
You are the Prediction & Synthesis Specialist.

Your mandate: Produce probabilistic race predictions. You are NOT allowed to
give vague answers. Every prediction must have a stated probability and reasoning.

You will be given findings from ALL other departments. Synthesize them.

Focus areas:
  - Race winner: top 3 candidates with estimated probabilities (must sum to ≤100%)
  - Podium combinations: which 3-driver combos are most likely?
  - Tyre strategy: predicted primary strategy per top team
  - Qualifying prediction: top 5 order with reasoning
  - Wildcards: 1-2 scenarios that could upset the expected order
  - Key watchpoints: the 3 most important moments in the race to watch
  - Championship impact: how does each podium scenario change the WDC/WCC gap?

{_BASE_TOOLS_GUIDANCE}

Output format — return ONLY this JSON:
{{
  "answer_md": "<full prediction report with probabilities>",
  "confidence": <0.0-1.0>,
  "tags": ["prediction", ...],
  "evidence": [...],
  "follow_up_questions": [],
  "key_claim": "<single sentence: your headline prediction>",
  "structured_predictions": {{
    "race_winner": [{{"driver": "<name>", "team": "<team>", "probability": <0-1>, "reasoning": "<why>"}}],
    "podium_drivers": ["<driver1>", "<driver2>", "<driver3>"],
    "qualifying_top5": ["<d1>", "<d2>", "<d3>", "<d4>", "<d5>"],
    "primary_strategies": {{"<team>": "<strategy e.g. S-M or M-H>"}},
    "wildcards": ["<scenario>"],
    "key_watchpoints": ["<moment>"],
    "championship_scenarios": [{{"result": "<who wins>", "wdc_gap_change": "<delta>"}}]
  }}
}}
""",

    "general": f"""\
You are a General F1 Research Specialist.
Investigate the question thoroughly using all available tools.

{_BASE_TOOLS_GUIDANCE}

Output format — return ONLY this JSON:
{{
  "answer_md": "<findings>",
  "confidence": <0.0-1.0>,
  "tags": [],
  "evidence": [...],
  "follow_up_questions": [...],
  "key_claim": "<single sentence summary>"
}}
""",
}


# ─────────────────────────────────────────────
# Prompt builders
# ─────────────────────────────────────────────

def build_specialist_prompt(
    question: ResearchQuestion,
    context_snapshot: dict[str, Any],
    prior_findings_summary: str = "",
) -> str:
    ctx_str = json.dumps(context_snapshot, ensure_ascii=False, indent=2)
    prompt_parts = [
        f"UTC TIME: {datetime.now(timezone.utc).isoformat()}",
        f"\nYOUR QUESTION (id={question.id}):\n{question.question}",
        f"\nAVAILABLE CONTEXT:\n{ctx_str}",
    ]
    if prior_findings_summary:
        prompt_parts.append(
            f"\nOTHER DEPARTMENTS HAVE FOUND (use to inform your analysis):\n{prior_findings_summary}"
        )
    prompt_parts.append(
        "\nBegin your investigation. Use tools freely. Think out loud. "
        "Return your final JSON answer when confident."
    )
    return "\n".join(prompt_parts)


def build_debate_prompt(
    finding: SpecialistFinding,
    challenger_dept: str,
    all_findings_summary: str,
) -> str:
    return (
        f"You are the {challenger_dept.upper()} specialist acting as a critical reviewer.\n\n"
        f"ALL CURRENT FINDINGS SUMMARY:\n{all_findings_summary}\n\n"
        f"FINDING TO CHALLENGE (from {finding.department} dept):\n"
        f"Question: {finding.question}\n"
        f"Answer summary: {finding.answer_md[:600]}\n"
        f"Confidence: {finding.confidence}\n"
        f"Key claim: next\n\n"
        "Your job: identify the single most important weakness, assumption, or missing piece "
        "in this finding. If you think the finding is solid, say so clearly.\n\n"
        "Return ONLY JSON:\n"
        '{"challenge": "<specific objection or \'FINDING IS SOLID\'>",'
        ' "confidence_delta": <-0.3 to +0.1>,'
        ' "suggested_fix": "<what evidence would resolve your challenge>"}'
    )


def build_resolution_prompt(
    finding: SpecialistFinding,
    challenge: str,
    suggested_fix: str,
) -> str:
    return (
        f"You are the {finding.department.upper()} specialist.\n\n"
        f"Your finding: {finding.answer_md[:800]}\n\n"
        f"A colleague challenged you: {challenge}\n"
        f"They suggested: {suggested_fix}\n\n"
        "Either: (a) use a tool to gather the suggested evidence and update your finding, "
        "or (b) explain concisely why your finding stands despite this challenge.\n\n"
        "Return ONLY JSON:\n"
        '{"resolution": "<your response>", "updated_confidence": <0.0-1.0>, '
        '"answer_update": "<updated key claim or empty string if unchanged>"}'
    )


# ─────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def parse_specialist_finding(
    question: ResearchQuestion,
    raw_text: str,
    exploration_depth: int,
) -> SpecialistFinding:
    obj = _extract_json(raw_text)

    conf_raw = obj.get("confidence", 0.5)
    try:
        conf = float(conf_raw)
    except Exception:
        conf = 0.5
    conf = max(0.0, min(1.0, conf))

    evidence = []
    for e in (obj.get("evidence") or []):
        if not isinstance(e, dict):
            continue
        evidence.append({
            "source_type": e.get("source_type") or "web",
            "source_id": e.get("source_id") or e.get("url") or "unknown",
            "title": e.get("title"),
            "quote": e.get("quote"),
            "metadata": e.get("metadata") if isinstance(e.get("metadata"), dict) else {},
        })

    return SpecialistFinding(
        question_id=question.id,
        department=question.department,
        question=question.question,
        answer_md=str(obj.get("answer_md") or raw_text[:2000]),
        confidence=conf,
        tags=obj.get("tags") or [question.department],
        evidence=evidence,
        follow_up_questions=obj.get("follow_up_questions") or [],
        follow_up_allowed=question.follow_up_allowed,
        exploration_depth=exploration_depth,
        raw_tool_calls=[],
    )


def parse_debate_challenge(
    raw_text: str,
    challenger_dept: str,
    target_question_id: str,
) -> DebateChallenge | None:
    obj = _extract_json(raw_text)
    if not obj:
        return None
    return DebateChallenge(
        challenger_dept=challenger_dept,
        target_question_id=target_question_id,
        challenge=str(obj.get("challenge") or ""),
        resolution="",
        confidence_delta=float(obj.get("confidence_delta") or 0.0),
    )


def parse_resolution(raw_text: str) -> dict:
    return _extract_json(raw_text)
