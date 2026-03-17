from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..kb import JsonlKnowledgeBase
from ..tools import _openf1_get


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_next_race_openf1(year: int = 2026) -> dict[str, Any] | None:
    """Deterministically pick next scheduled Race session (OpenF1)."""

    today = datetime.now(timezone.utc)
    races = _openf1_get("sessions", params={"year": year, "session_type": "Race"})
    races_sorted = sorted(races, key=lambda r: r.get("date_start") or "9999")

    for r in races_sorted:
        ds = r.get("date_start")
        if not ds:
            continue
        try:
            dt = datetime.fromisoformat(ds.replace("Z", "+00:00"))
        except Exception:
            continue
        if dt >= today:
            return r

    return races_sorted[-1] if races_sorted else None


def summarize_weather_openf1(next_race: dict[str, Any] | None) -> dict[str, Any]:
    """Small weather summary for a race meeting using OpenF1 weather endpoint."""

    if not next_race:
        return {"ok": False, "error": "no_next_race"}

    meeting_key = next_race.get("meeting_key")
    if not meeting_key:
        return {"ok": False, "error": "no_meeting_key"}

    rows = _openf1_get("weather", params={"meeting_key": meeting_key})
    if not rows:
        return {"ok": True, "meeting_key": meeting_key, "samples": 0}

    # crude aggregates
    temps = [r.get("air_temperature") for r in rows if isinstance(r.get("air_temperature"), (int, float))]
    winds = [r.get("wind_speed") for r in rows if isinstance(r.get("wind_speed"), (int, float))]
    rain = [r.get("rainfall") for r in rows if isinstance(r.get("rainfall"), (int, float))]

    def _avg(xs: list[float]) -> float | None:
        return float(sum(xs) / len(xs)) if xs else None

    return {
        "ok": True,
        "meeting_key": meeting_key,
        "samples": len(rows),
        "air_temp_avg": _avg([float(x) for x in temps]) if temps else None,
        "wind_speed_avg": _avg([float(x) for x in winds]) if winds else None,
        "rainfall_avg": _avg([float(x) for x in rain]) if rain else None,
        "updated_at": _utc_iso(),
    }


def persist_department_snapshot(kb: JsonlKnowledgeBase, key: str, value: dict[str, Any]) -> None:
    """Write a durable note to the KB (human-readable trace)."""

    kb.add(
        namespace="corp",
        text=f"[{_utc_iso()}] dept_snapshot {key}: {json.dumps(value, ensure_ascii=False)[:1500]}",
        metadata={"dept": key},
    )
