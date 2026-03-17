from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_core.messages import SystemMessage

from .agent_graph import SYSTEM_PROMPT, build_agent, run_agent
from .kb import JsonlKnowledgeBase
from .settings import Settings


def _get_agent(agents_cache: dict[str, object], key: str, settings: Settings, kb: JsonlKnowledgeBase):
    if key not in agents_cache:
        agents_cache[key] = build_agent(settings, kb)
    return agents_cache[key]


def _specialization_system(agent_type: str, namespace: str) -> str:
    """Scoped system prompts to force tool usage and reduce generic web browsing."""

    base = (
        "You must rely on OpenF1 tools for quantitative claims. "
        "Use web_search followed by scrape_webpage to read full news articles for context. "
        f"Store durable findings in KB namespace '{namespace}'."
    )

    if agent_type == "news":
        return (
            base
            + "\nYou are the News Signal Agent. Find high-signal updates: upgrades, penalties, injuries,"
            " PU components, regulation clarifications. Prefer official/team/FIA sources."
            " Use web_search -> scrape_webpage to read the actual articles and summarize the true impact."
        )

    if agent_type == "season_form":
        return (
            base
            + "\nYou are the Season Form Agent. Focus on season-wise performance: race finishes,"
            " points trends, consistency, and track-type sensitivity. Use OpenF1 race sessions and"
            " session_result across the year. Write python code using python_repl to calculate point averages and consistency metrics!"
        )

    if agent_type == "telemetry":
        return (
            base
            + "\nYou are the Telemetry/Pace Agent. "
            " YOU MUST use the `python_repl` tool (with `requests` and `pandas`) to download lap times and telemetry from `https://api.openf1.org/v1/laps` and `intervals`. "
            "DO NOT use the `openf1_laps` or `openf1_intervals` tool directly, it will crash your context window!"
            " Calculate mean/median pace, exclude outliers, and find true statistical advantages."
        )

    if agent_type == "tyre_weather":
        return (
            base
            + "\nYou are the Tyre & Weather Agent. "
            " YOU MUST use `python_repl` with `requests` to download `stints` and `weather` data directly from OpenF1 to model tyre degradation (lap time increase per lap) on different compounds. Do not use the OpenF1 tools directly for large datasets."
        )

    if agent_type == "predict_pipeline":
        return (
            base
            + "\nYou are the Synthesis Agent. You will be given structured findings from other agents." 
            "Combine them into the final JSON output required by the caller, with evidence, without hallucinating."
        )

    return base


async def run_pipeline(
    *,
    settings: Settings,
    kb: JsonlKnowledgeBase,
    agents_cache: dict[str, object],
    agent_type: str,
    user_message: str,
    namespace: str,
    extra_system: Optional[str],
) -> dict[str, Any]:
    """Entry point for /agent/run supporting specialized agents and an orchestrated pipeline.

    Returns dict compatible with AgentRunResponse: {answer, tool_calls, trace?}.
    """

    log = logging.getLogger("f1_agents.pipeline")
    t0 = time.time()

    # Normalize
    agent_type = (agent_type or "general").strip().lower()

    # Build specialization prompt
    specialization = _specialization_system(agent_type, namespace)
    combined_extra = specialization
    if extra_system:
        combined_extra = combined_extra + "\n\n" + extra_system

    # Simple single-agent modes
    if agent_type in {"general", "news", "season_form", "telemetry", "tyre_weather"}:
        agent = _get_agent(agents_cache, "general_agent", settings, kb)
        result = await run_agent(agent, user_message=user_message, extra_system=combined_extra)
        result["trace"] = {"agent_type": agent_type, "duration_ms": int((time.time() - t0) * 1000)}
        return result

    # Orchestrated pipeline: run specialized steps then synthesize
    if agent_type == "predict_pipeline":
        agent = _get_agent(agents_cache, "general_agent", settings, kb)

        # --- Pre-step: pick the next race deterministically from OpenF1 ---
        try:
            from .tools import _openf1_get

            today = datetime.now(timezone.utc)
            races = _openf1_get("sessions", params={"year": 2026, "session_type": "Race"})
            races_sorted = sorted(
                races,
                key=lambda r: r.get("date_start") or "9999-12-31T00:00:00+00:00",
            )
            # Find:
            # 1) the next scheduled race (>= today)
            # 2) the most recent race with results (session_result exists)
            next_scheduled = None
            for r in races_sorted:
                ds = r.get("date_start")
                if not ds:
                    continue
                try:
                    dt = datetime.fromisoformat(ds.replace("Z", "+00:00"))
                except Exception:
                    continue
                if dt >= today:
                    next_scheduled = r
                    break

            latest_with_results = None
            for r in reversed(races_sorted):
                sk = r.get("session_key")
                if not sk:
                    continue
                try:
                    # OpenF1 returns 404 with {"detail":"No results found."} when results aren't available.
                    _openf1_get("session_result", params={"session_key": sk, "position<=": 1})
                    latest_with_results = r
                    break
                except Exception:
                    continue

            # Use the next scheduled race for context; but if results aren't available yet (e.g. future race),
            # season-form computations should anchor on the latest race with results.
            next_race = next_scheduled or latest_with_results or (races_sorted[-1] if races_sorted else None)
            anchor_race_for_form = latest_with_results or next_race
        except Exception:
            next_race = None
            anchor_race_for_form = None

        # Step 1: season form
        season = await run_agent(
            agent,
            user_message=(
                "Compute season-wise performance signals for 2026: top drivers/teams by recent *completed* race results, "
                "consistency, and momentum. Use OpenF1 race sessions + session_result across the year. "
                "Return bullet insights + cite OpenF1 endpoints you used."
                + (f"\nNext scheduled race context: {json.dumps(next_race)}" if next_race else "")
                + (
                    f"\nMost recent race with results (anchor for form): {json.dumps(anchor_race_for_form)}"
                    if anchor_race_for_form
                    else ""
                )
            ),
            extra_system=_specialization_system("season_form", namespace),
        )

        # Step 2: tyre/weather
        tyre_weather = await run_agent(
            agent,
            user_message=(
                "Analyze tyre usage and weather patterns relevant to the next race. "
                "First, fetch weather for the next race session_key if available; then compare with season race weather samples. "
                "Use OpenF1 stints across races (and any available stints for the next race weekend). "
                "Identify likely degradation/strategy tendencies and which car traits benefit."
                + (f"\nNext race context: {json.dumps(next_race)}" if next_race else "")
            ),
            extra_system=_specialization_system("tyre_weather", namespace),
        )

        # Step 3: news signals
        news = await run_agent(
            agent,
            user_message=(
                "Gather only high-signal recent F1 updates that could impact the next race (upgrades, penalties, "
                "driver fitness, reliability, regulation clarifications). Provide 5-8 items with sources. "
                "When searching, include team/driver names or specific keywords (e.g. 'upgrade package', 'power unit penalty', 'gearbox penalty', 'stewards decision'). "
                "If you get irrelevant results, retry using more specific F1 terms and avoid generic words like 'formula'."
                + (f"\nNext race context: {json.dumps(next_race)}" if next_race else "")
            ),
            extra_system=_specialization_system("news", namespace),
        )

        # Step 4: synthesize final
        synth_extra = combined_extra + (
            "\n\nYou will be given three JSON-ish text blocks (season_form, tyre_weather, news). "
            "Synthesize them into the required final JSON output."
        )

        synth_message = (
            "SYNTHESIZE INTO FINAL ANSWER.\n\n"
            "NEXT_RACE_OPENF1:\n"
            f"{json.dumps(next_race) if next_race else 'null'}\n\n"
            "SEASON_FORM_FINDINGS:\n"
            f"{season['answer']}\n\n"
            "TYRE_WEATHER_FINDINGS:\n"
            f"{tyre_weather['answer']}\n\n"
            "NEWS_FINDINGS:\n"
            f"{news['answer']}\n\n"
            "Now produce the final answer JSON." 
        )

        final = await run_agent(agent, user_message=synth_message, extra_system=synth_extra)

        # Merge traces for observability
        final["trace"] = {
            "agent_type": agent_type,
            "duration_ms": int((time.time() - t0) * 1000),
            "steps": {
                "season_form": {"answer_chars": len(season.get("answer") or ""), "tool_calls": len(season.get("tool_calls") or [])},
                "tyre_weather": {"answer_chars": len(tyre_weather.get("answer") or ""), "tool_calls": len(tyre_weather.get("tool_calls") or [])},
                "news": {"answer_chars": len(news.get("answer") or ""), "tool_calls": len(news.get("tool_calls") or [])},
            },
        }

        # Include tool calls from all steps (best-effort)
        tool_calls: list[dict[str, Any]] = []
        tool_calls.extend(season.get("tool_calls") or [])
        tool_calls.extend(tyre_weather.get("tool_calls") or [])
        tool_calls.extend(news.get("tool_calls") or [])
        tool_calls.extend(final.get("tool_calls") or [])
        final["tool_calls"] = tool_calls

        return final

    raise ValueError(f"Unknown agent_type: {agent_type}")
