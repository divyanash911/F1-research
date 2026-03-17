from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool

from .fastf1_client import fastf1_session, safe_load


@tool
def fastf1_event_schedule(year: int = 2026) -> str:
    """Fetch the FastF1 event schedule for a year. Returns JSON string.

    Useful for 'next race' and calendar context with official event naming.
    """

    import fastf1  # type: ignore

    fastf1.Cache.enable_cache("./data/fastf1_cache")
    sched = fastf1.get_event_schedule(year)

    # Return a lightweight subset
    rows: list[dict[str, Any]] = []
    for _, r in sched.iterrows():
        rows.append(
            {
                "RoundNumber": int(r.get("RoundNumber")) if r.get("RoundNumber") is not None else None,
                "EventName": str(r.get("EventName")) if r.get("EventName") is not None else None,
                "Country": str(r.get("Country")) if r.get("Country") is not None else None,
                "Location": str(r.get("Location")) if r.get("Location") is not None else None,
                "EventDate": str(r.get("EventDate")) if r.get("EventDate") is not None else None,
            }
        )

    return json.dumps(rows, ensure_ascii=False)


@tool
def fastf1_completed_event_schedule(year: int = 2026) -> str:
    """Fetch FastF1 event schedule but only include completed events.

    We treat an event as "completed" when its EventDate is <= today (UTC).
    This avoids agents selecting future races/sessions which often have no timing data.
    Returns a JSON array like fastf1_event_schedule.
    """

    import fastf1  # type: ignore

    fastf1.Cache.enable_cache("./data/fastf1_cache")
    sched = fastf1.get_event_schedule(year)

    today = datetime.now(timezone.utc).date()

    rows: list[dict[str, Any]] = []
    for _, r in sched.iterrows():
        ed = r.get("EventDate")
        # pandas Timestamp => to_pydatetime; otherwise parse as date-ish string.
        event_date = None
        try:
            if ed is not None and hasattr(ed, "to_pydatetime"):
                event_date = ed.to_pydatetime().date()
        except Exception:
            event_date = None
        if event_date is None:
            try:
                if ed is not None:
                    event_date = datetime.fromisoformat(str(ed)).date()
            except Exception:
                event_date = None

        if event_date is None or event_date > today:
            continue

        rows.append(
            {
                "RoundNumber": int(r.get("RoundNumber")) if r.get("RoundNumber") is not None else None,
                "EventName": str(r.get("EventName")) if r.get("EventName") is not None else None,
                "Country": str(r.get("Country")) if r.get("Country") is not None else None,
                "Location": str(r.get("Location")) if r.get("Location") is not None else None,
                "EventDate": str(r.get("EventDate")) if r.get("EventDate") is not None else None,
            }
        )

    return json.dumps(rows, ensure_ascii=False)


@tool
def fastf1_session_summary(year: int, gp: str, session: str) -> str:
    """Load a FastF1 session and return a small summary (laps count, drivers list).

    Args:
      year: season year
      gp: Grand Prix name or round number as string
      session: e.g. 'R', 'Q', 'FP1', 'FP2', 'FP3', 'S', 'SQ'
    """

    s = fastf1_session(year, gp, session)
    summary = safe_load(s, laps=True, telemetry=False, weather=True)
    return json.dumps(summary, ensure_ascii=False)


@tool
def fastf1_driver_pace_overview(year: int, gp: str, session: str) -> str:
    """Compute a quick pace overview using FastF1 laps data.

    Returns per-driver median lap time (excluding in/out laps and obvious outliers).
    This stays small enough for LLM context, while being far richer than a naive summary.
    """

    import numpy as np

    s = fastf1_session(year, gp, session)
    safe_load(s, laps=True, telemetry=False, weather=False)

    laps = s.laps
    if laps is None or len(laps) == 0:
        return json.dumps({"error": "No laps available"}, ensure_ascii=False)

    # Filter: remove in/out laps and laps without LapTime
    try:
        laps = laps.pick_quicklaps()  # FastF1 helper
    except Exception:
        # fallback: basic filtering
        laps = laps[laps["LapTime"].notnull()]

    out: list[dict[str, Any]] = []
    for drv in sorted(set(laps["Driver"].astype(str).tolist())):
        dl = laps[laps["Driver"].astype(str) == drv]
        lt = dl["LapTime"].dt.total_seconds().to_numpy(dtype=float)
        lt = lt[np.isfinite(lt)]
        if lt.size < 3:
            continue
        # Robust: median + MAD-based trimming
        med = float(np.median(lt))
        mad = float(np.median(np.abs(lt - med))) or 0.0
        if mad > 0:
            keep = np.abs(lt - med) <= 4.0 * (1.4826 * mad)
            lt2 = lt[keep]
        else:
            lt2 = lt
        out.append(
            {
                "driver": drv,
                "laps": int(lt2.size),
                "median": float(np.median(lt2)),
                "p25": float(np.percentile(lt2, 25)),
                "p75": float(np.percentile(lt2, 75)),
            }
        )

    out.sort(key=lambda x: x["median"])
    return json.dumps(out[:25], ensure_ascii=False)


@tool
def fastf1_compare_drivers_minisectors(
    year: int,
    gp: str,
    session: str,
    driver_a: str,
    driver_b: str,
    minisectors: int = 25,
) -> str:
    """Compare two drivers using FastF1 minisectors (distance-based segmentation).

    This produces a small, context-safe summary:
    - which driver is faster in how many minisectors
    - the largest delta minisectors

    Notes:
    - Uses each driver's *fastest* lap in the session.
    - Minisectors are computed by slicing the lap distance into N equal bins.
    """

    import numpy as np
    import pandas as pd

    s = fastf1_session(year, gp, session)
    safe_load(s, laps=True, telemetry=True, weather=False)

    laps = s.laps
    if laps is None or len(laps) == 0:
        return json.dumps({"error": "No laps available"}, ensure_ascii=False)

    def _fastest_lap(drv: str):
        dl = laps.pick_driver(drv)
        try:
            dl = dl.pick_quicklaps()
        except Exception:
            dl = dl[dl["LapTime"].notnull()]
        if len(dl) == 0:
            return None
        return dl.sort_values("LapTime").iloc[0]

    la = _fastest_lap(driver_a)
    lb = _fastest_lap(driver_b)
    if la is None or lb is None:
        return json.dumps({"error": "Missing fastest lap for one or both drivers"}, ensure_ascii=False)

    ta = la.get_telemetry().copy()
    tb = lb.get_telemetry().copy()

    # Ensure distance exists
    if "Distance" not in ta.columns or "Distance" not in tb.columns:
        return json.dumps({"error": "Telemetry missing Distance"}, ensure_ascii=False)

    max_d = float(min(ta["Distance"].max(), tb["Distance"].max()))
    if not np.isfinite(max_d) or max_d <= 0:
        return json.dumps({"error": "Invalid distance range"}, ensure_ascii=False)

    edges = np.linspace(0.0, max_d, minisectors + 1)

    def _minisector_df(t: pd.DataFrame) -> pd.DataFrame:
        d = t[["Distance", "Time"]].copy()
        d = d[d["Distance"].between(0.0, max_d)]
        # FastF1 'Time' is timedelta
        d["t_s"] = d["Time"].dt.total_seconds()
        d = d.dropna(subset=["Distance", "t_s"])
        d["ms"] = np.clip(np.digitize(d["Distance"].to_numpy(), edges) - 1, 0, minisectors - 1)

        # minisector time approx: (max t - min t) within minisector
        g = d.groupby("ms", as_index=False).agg(t_min=("t_s", "min"), t_max=("t_s", "max"))
        g["dt"] = g["t_max"] - g["t_min"]
        g = g[["ms", "dt"]]
        return g

    ma = _minisector_df(ta)
    mb = _minisector_df(tb)
    m = ma.merge(mb, on="ms", how="inner", suffixes=("_a", "_b"))
    if len(m) == 0:
        return json.dumps({"error": "No minisector overlap"}, ensure_ascii=False)

    m["delta_a_minus_b"] = m["dt_a"] - m["dt_b"]
    faster_a = int((m["delta_a_minus_b"] < 0).sum())
    faster_b = int((m["delta_a_minus_b"] > 0).sum())

    top = m.reindex(m["delta_a_minus_b"].abs().sort_values(ascending=False).index).head(8)
    top_list = [
        {
            "minisector": int(r.ms),
            "delta_a_minus_b_s": float(r.delta_a_minus_b),
        }
        for r in top.itertuples(index=False)
    ]

    return json.dumps(
        {
            "year": year,
            "gp": gp,
            "session": session,
            "driver_a": driver_a,
            "driver_b": driver_b,
            "minisectors": minisectors,
            "faster_ms": {"a": faster_a, "b": faster_b, "tie": int(len(m) - faster_a - faster_b)},
            "largest_deltas": top_list,
            "notes": "Negative delta means driver_a faster in that minisector.",
        },
        ensure_ascii=False,
    )


@tool
def fastf1_stint_degradation_summary(year: int, gp: str, session: str) -> str:
    """Estimate stint degradation slopes per driver using FastF1 laps.

    Output stays compact: per driver, per stint, a linear slope (s/lap) of lap time vs lap number in stint.
    This is not a full tire model, but it is a strong quantitative signal for strategy insights.
    """

    import numpy as np

    s = fastf1_session(year, gp, session)
    safe_load(s, laps=True, telemetry=False, weather=False)
    laps = s.laps
    if laps is None or len(laps) == 0:
        return json.dumps({"error": "No laps available"}, ensure_ascii=False)

    # Ensure essentials
    df = laps.copy()
    if "LapTime" not in df.columns:
        return json.dumps({"error": "LapTime missing"}, ensure_ascii=False)

    # Filter usable laps
    try:
        df = df.pick_quicklaps()
    except Exception:
        df = df[df["LapTime"].notnull()]

    # Stint numbering can be absent; FastF1 provides 'Stint' for races typically.
    if "Stint" not in df.columns:
        return json.dumps({"error": "Stint column not available for this session"}, ensure_ascii=False)

    out: list[dict[str, Any]] = []
    for drv in sorted(set(df["Driver"].astype(str).tolist())):
        dl = df[df["Driver"].astype(str) == drv]
        for stint_id in sorted(set(dl["Stint"].dropna().astype(int).tolist())):
            sl = dl[dl["Stint"].astype(float) == float(stint_id)].sort_values("LapNumber")
            if len(sl) < 6:
                continue
            y = sl["LapTime"].dt.total_seconds().to_numpy(dtype=float)
            x = np.arange(len(y), dtype=float)
            if not np.isfinite(y).all():
                continue
            # linear regression slope
            slope = float(np.polyfit(x, y, 1)[0])
            out.append(
                {
                    "driver": drv,
                    "stint": int(stint_id),
                    "laps": int(len(y)),
                    "degradation_s_per_lap": slope,
                    "compound": str(sl.iloc[0].get("Compound")) if "Compound" in sl.columns else None,
                }
            )

    # Most interesting first: highest degradation
    out.sort(key=lambda r: (r["degradation_s_per_lap"] if r["degradation_s_per_lap"] is not None else -999), reverse=True)
    return json.dumps(out[:60], ensure_ascii=False)
