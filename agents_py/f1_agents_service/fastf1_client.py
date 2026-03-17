from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def ensure_fastf1_cache() -> Path:
    """Ensure FastF1 cache is enabled.

    FastF1 is heavily cached by design; without cache it can be slow and can
    repeatedly hit upstream endpoints.
    """

    cache_dir = Path(os.getenv("FASTF1_CACHE_DIR", "./data/fastf1_cache")).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)

    import fastf1  # type: ignore

    # Avoid re-enabling multiple times; FastF1 is tolerant of repeated calls.
    fastf1.Cache.enable_cache(str(cache_dir))
    return cache_dir


def fastf1_session(year: int, gp: str | int, session: str):
    """Get a FastF1 session object with cache enabled."""

    ensure_fastf1_cache()
    import fastf1  # type: ignore

    return fastf1.get_session(year, gp, session)


def safe_load(session_obj, *, laps: bool = True, telemetry: bool = True, weather: bool = True) -> dict[str, Any]:
    """Load session data with FastF1 and return a small summary.

    The full FastF1 objects are large; we return a minimal summary for logging.
    """

    # FastF1 load signatures vary slightly across versions; keep kwargs simple.
    session_obj.load(laps=laps, telemetry=telemetry, weather=weather)

    summary: dict[str, Any] = {
        "event": getattr(getattr(session_obj, "event", None), "EventName", None)
        or getattr(getattr(session_obj, "event", None), "EventName", ""),
        "session": getattr(session_obj, "name", None),
        "year": getattr(getattr(session_obj, "event", None), "year", None),
    }

    try:
        summary["laps"] = int(len(session_obj.laps)) if getattr(session_obj, "laps", None) is not None else 0
    except Exception:
        summary["laps"] = None

    try:
        summary["drivers"] = list(getattr(session_obj, "drivers", []) or [])
    except Exception:
        summary["drivers"] = []

    return summary
