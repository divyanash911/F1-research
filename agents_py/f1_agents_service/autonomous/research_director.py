"""
research_director.py
────────────────────
The Research Director is the meta-agent that opens every research cycle.

It reads ALL available signals (next race, standings, recent results, news,
weather, prior-season same-track data) and produces a structured ResearchAgenda:
a ranked list of questions each specialist agent will independently investigate.

The Director deliberately avoids fixed question templates. Every run it must
reason from scratch about what is actually interesting *this week*, which forces
fresh, non-repetitive briefs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("f1_agents.research_director")


# ─────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────

@dataclass
class ResearchQuestion:
    """A single question the Director wants investigated."""
    id: str
    department: str          # pace | strategy | telemetry | weather | news | prediction
    question: str            # open-ended, plain English
    priority: int            # 1 (highest) … 5 (lowest)
    context_keys: list[str]  # state keys the specialist should pull when answering
    follow_up_allowed: bool = True  # whether the specialist may spawn sub-questions


@dataclass
class ResearchAgenda:
    """Full agenda produced by the Director for one research cycle."""
    run_id: str
    generated_at: str
    next_race_name: str
    questions: list[ResearchQuestion] = field(default_factory=list)
    director_notes: str = ""          # free-form reasoning the Director wants preserved
    key_unknowns: list[str] = field(default_factory=list)   # things we couldn't answer yet


# ─────────────────────────────────────────────
# Prompt builders
# ─────────────────────────────────────────────

_DIRECTOR_SYSTEM = """\
You are the F1 Research Director. Your job is to design this week's research agenda.

You will be given a JSON snapshot of everything currently known:
  - next_race       : circuit, date, location
  - recent_results  : last 3 races (winner, fastest lap, key incidents)
  - standings       : current WDC and WCC standings with gap deltas
  - weather_forecast: forecast for race weekend
  - news_signals    : recent headlines, upgrades, penalties, driver news
  - historical_same_track: results from same circuit last 1-2 seasons
  - telemetry_summary: high-level season-to-date pace trends

Your output MUST be a single JSON object with this exact schema:
{
  "next_race_name": "<string>",
  "director_notes": "<your reasoning, max 300 words>",
  "key_unknowns": ["<thing we don't yet have data on>", ...],
  "questions": [
    {
      "id": "q1",
      "department": "<pace|strategy|telemetry|weather|news|prediction>",
      "question": "<specific open-ended question>",
      "priority": <1-5>,
      "context_keys": ["<state key>", ...],
      "follow_up_allowed": <true|false>
    }
  ]
}

Rules:
- Generate 8–14 questions covering ALL departments.
- At least 2 questions must be explicitly about the PREDICTION layer
  (race winner probabilities, podium, strategy window).
- Questions must be specific to THIS race week — not generic F1 questions.
- If there is a major news event (penalty, crash, upgrade), dedicate 1-2 questions to its downstream impact.
- Vary question depth: some should be narrow data lookups, others genuinely open-ended hypotheses.
- key_unknowns should list gaps in the snapshot data that would change your analysis.
- Do NOT repeat question patterns from prior runs. Be genuinely curious.
- Return ONLY the JSON object, no markdown, no preamble.
"""


def build_director_prompt(snapshot: dict[str, Any], prior_run_headlines: list[str]) -> str:
    prior_context = ""
    if prior_run_headlines:
        headlines_str = "\n".join(f"  - {h}" for h in prior_run_headlines[-5:])
        prior_context = (
            f"\nPRIOR RUN HEADLINES (avoid repeating these angles):\n{headlines_str}\n"
        )

    return (
        f"Current UTC time: {datetime.now(timezone.utc).isoformat()}\n\n"
        f"KNOWLEDGE SNAPSHOT:\n{json.dumps(snapshot, ensure_ascii=False, indent=2)}\n"
        f"{prior_context}\n"
        "Design the research agenda for this race week."
    )


# ─────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────

def parse_agenda(run_id: str, raw_text: str) -> ResearchAgenda:
    """Parse the Director's JSON output into a ResearchAgenda."""
    import re

    text = (raw_text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]

    try:
        obj = json.loads(text)
    except Exception:
        logger.warning("director_parse_failed raw=%s", raw_text[:200])
        return _fallback_agenda(run_id)

    questions = []
    for i, q in enumerate(obj.get("questions") or []):
        if not isinstance(q, dict):
            continue
        questions.append(ResearchQuestion(
            id=q.get("id") or f"q{i+1}",
            department=q.get("department") or "general",
            question=q.get("question") or "",
            priority=int(q.get("priority") or 3),
            context_keys=q.get("context_keys") or [],
            follow_up_allowed=bool(q.get("follow_up_allowed", True)),
        ))

    return ResearchAgenda(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        next_race_name=str(obj.get("next_race_name") or "Unknown Race"),
        questions=sorted(questions, key=lambda x: x.priority),
        director_notes=str(obj.get("director_notes") or ""),
        key_unknowns=obj.get("key_unknowns") or [],
    )


def _fallback_agenda(run_id: str) -> ResearchAgenda:
    """Minimal agenda used when parsing fails — still covers all departments."""
    departments = ["pace", "strategy", "telemetry", "weather", "news", "prediction"]
    questions = [
        ResearchQuestion(
            id=f"fallback-{d}",
            department=d,
            question=f"What are the most important {d} factors for this race weekend?",
            priority=3,
            context_keys=[],
        )
        for d in departments
    ]
    # Add prediction questions
    questions += [
        ResearchQuestion(
            id="fallback-pred-1",
            department="prediction",
            question="Who are the likely race winner and podium finishers, and why?",
            priority=1,
            context_keys=[],
        ),
        ResearchQuestion(
            id="fallback-pred-2",
            department="prediction",
            question="What tyre strategy windows exist and which teams are best positioned?",
            priority=1,
            context_keys=[],
        ),
    ]
    return ResearchAgenda(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        next_race_name="Unknown Race",
        questions=questions,
        director_notes="Fallback agenda — director parse failed.",
    )