"""
F1 Research Program - FastF1 Telemetry Tools
Fine-grained tools for all aspects of F1 telemetry analysis.
Each tool is a self-contained unit agents can call autonomously.
"""

import json
import os
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional
from crewai.tools import tool

# Suppress matplotlib warnings in headless environments
warnings.filterwarnings("ignore", category=UserWarning)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import fastf1
import fastf1.plotting

# ── FastF1 cache setup ──────────────────────────────────────────────────────
CACHE_DIR = Path(os.getenv("FASTF1_CACHE_DIR", "./telemetry_cache"))
CACHE_DIR.mkdir(exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))

PLOTS_DIR = Path("insights/plots")
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACTS_DIR = Path("logs/tool_artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

SEASON = int(os.getenv("F1_SEASON", "2026"))

# ── Session loader (cached) ─────────────────────────────────────────────────
_session_cache: dict = {}

def _load_session(year: int, event, session_type: str):
    """Load and cache a FastF1 session object."""
    key = f"{year}_{event}_{session_type}"
    if key not in _session_cache:
        try:
            sess = fastf1.get_session(year, event, session_type)
            sess.load(telemetry=True, laps=True, weather=True, messages=True)
            _session_cache[key] = sess
        except Exception as e:
            return None, str(e)
    return _session_cache[key], None


def _fmt_timedelta(td) -> str:
    """Format timedelta to readable string."""
    if pd.isna(td):
        return "N/A"
    total_seconds = td.total_seconds()
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:06.3f}"


def _safe_json_loads(payload: str) -> dict:
    try:
        data = json.loads(payload)
        return data if isinstance(data, dict) else {"data": data}
    except Exception:
        return {"error": "invalid_json", "raw_preview": str(payload)[:1000]}


def _write_tool_artifact(tool_name: str, payload: dict) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = ARTIFACTS_DIR / f"{tool_name}_{ts}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def _call_tool_func(tool_obj, **kwargs) -> str:
    """Call the underlying Python function for a CrewAI Tool or plain callable."""
    func = getattr(tool_obj, "func", None)
    if callable(func):
        return func(**kwargs)
    if callable(tool_obj):
        return tool_obj(**kwargs)
    raise TypeError(f"Object {tool_obj!r} is not callable and has no callable .func")


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 1: Schedule & Session Info
# ══════════════════════════════════════════════════════════════════════════════
@tool("get_f1_season_schedule")
def get_season_schedule(year: int = SEASON) -> str:
    """
    Retrieve the full F1 season schedule including all race events,
    dates, circuits, and locations. Returns upcoming and past races.
    Use this to know what races are coming up and what data is available.
    Input: year as integer (e.g. 2026)
    """
    try:
        year = int(year)
        # Try FastF1 first
        try:
            schedule = fastf1.get_event_schedule(year)
            rows = []
            now  = pd.Timestamp.now(tz="UTC")
            for _, row in schedule.iterrows():
                status = "✅ Past" if row["Session5Date"] < now else "⏳ Upcoming"
                rows.append({
                    "round":     int(row["RoundNumber"]),
                    "name":      row["EventName"],
                    "circuit":   row["Location"],
                    "country":   row["Country"],
                    "race_date": str(row["Session5Date"])[:10],
                    "status":    status,
                })
            return json.dumps({"season": year, "source": "fastf1", "events": rows}, indent=2)
        except Exception:
            pass

        # Fallback: static schedule
        from tools.f1_static_data import get_schedule
        from datetime import date
        events = get_schedule(year)
        today  = date.today().isoformat()
        rows   = []
        for e in events:
            status = "✅ Past" if e["race_date"] < today else "⏳ Upcoming"
            rows.append({**e, "status": status})
        return json.dumps({"season": year, "source": "static_fallback", "events": rows}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 2: Lap Times & Race Pace Analysis
# ══════════════════════════════════════════════════════════════════════════════
@tool("analyze_lap_times_and_pace")
def analyze_lap_times(event: str, session_type: str = "R", year: int = SEASON) -> str:
    """
    Deep analysis of lap times for all drivers in a session.
    Computes: median pace, std deviation, pace degradation per stint,
    fastest/slowest laps, lap time evolution, and outlier detection.
    session_type: 'R' (Race), 'Q' (Qualifying), 'FP1'/'FP2'/'FP3' (Practice).
    event: Race name or round number (e.g., 'Bahrain' or 1).
    """
    try:
        event_key = int(event) if event.isdigit() else event
    except:
        event_key = event

    sess, err = _load_session(year, event_key, session_type)
    if err:
        return json.dumps({"error": err})

    try:
        laps = sess.laps.copy()
        laps = laps[laps["LapTime"].notna()]
        laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()

        results = {}
        for driver in laps["Driver"].unique():
            d_laps = laps[laps["Driver"] == driver].copy()
            if len(d_laps) < 3:
                continue
            
            times      = d_laps["LapTimeSeconds"].values
            lap_nums   = d_laps["LapNumber"].values
            compounds  = d_laps["Compound"].tolist() if "Compound" in d_laps else []
            
            # Pace degradation: linear regression slope (seconds/lap)
            if len(times) >= 5:
                coeffs    = np.polyfit(lap_nums, times, 1)
                degrad    = round(float(coeffs[0]), 4)
            else:
                degrad    = None

            # Consistency: coefficient of variation
            cv = round(float(np.std(times) / np.mean(times) * 100), 3) if np.mean(times) > 0 else None

            results[driver] = {
                "laps_completed":    int(len(d_laps)),
                "fastest_lap":       _fmt_timedelta(d_laps["LapTime"].min()),
                "median_lap":        _fmt_timedelta(d_laps["LapTime"].median()),
                "mean_lap_seconds":  round(float(np.mean(times)), 3),
                "std_dev_seconds":   round(float(np.std(times)), 3),
                "consistency_cv_%":  cv,
                "pace_degr_s_per_lap": degrad,
                "compounds_used":    list(set(c for c in compounds if isinstance(c, str))),
                "lap_range":         [int(lap_nums.min()), int(lap_nums.max())],
            }

        # Ranking by median pace
        ranking = sorted(results.items(), key=lambda x: x[1].get("mean_lap_seconds", 999))
        gap_to_leader = {}
        if ranking:
            leader_pace = ranking[0][1]["mean_lap_seconds"]
            for driver, data in ranking:
                gap = round(data["mean_lap_seconds"] - leader_pace, 3)
                gap_to_leader[driver] = f"+{gap:.3f}s"

        return json.dumps({
            "event":       str(event),
            "year":        year,
            "session":     session_type,
            "total_laps":  int(len(laps)),
            "drivers":     results,
            "pace_ranking": [d for d, _ in ranking],
            "gaps_to_leader": gap_to_leader,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "trace": str(e.__class__.__name__)})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 3: Driver Telemetry Comparison
# ══════════════════════════════════════════════════════════════════════════════
@tool("compare_driver_telemetry")
def compare_driver_telemetry(event: str, driver1: str, driver2: str,
                              session_type: str = "Q", year: int = SEASON) -> str:
    """
    Compare detailed telemetry between two drivers on their fastest laps.
    Analyzes: speed traces, throttle/brake application, gear usage, DRS usage,
    braking points, acceleration zones, and sector-by-sector differences.
    driver1/driver2: 3-letter codes e.g. 'VER', 'HAM', 'LEC', 'NOR'.
    """
    try:
        event_key = int(event) if event.isdigit() else event
    except:
        event_key = event

    sess, err = _load_session(year, event_key, session_type)
    if err:
        return json.dumps({"error": err})

    try:
        results = {}
        for driver in [driver1.upper(), driver2.upper()]:
            d_laps = sess.laps.pick_driver(driver)
            if d_laps.empty:
                results[driver] = {"error": "No laps found"}
                continue
            
            fastest = d_laps.pick_fastest()
            tel     = fastest.get_car_data().add_distance()
            
            # Speed analysis
            speeds = tel["Speed"].values
            
            # Throttle application
            throttle = tel["Throttle"].values if "Throttle" in tel else np.array([])
            
            # Brake application  
            brake = tel["Brake"].values if "Brake" in tel else np.array([])
            
            # Gear distribution
            gears = tel["nGear"].values if "nGear" in tel else np.array([])
            gear_dist = {int(g): int(np.sum(gears == g)) for g in sorted(set(gears))} if len(gears) > 0 else {}
            
            # DRS
            drs = tel["DRS"].values if "DRS" in tel else np.array([])
            drs_active_pct = round(float(np.sum(drs > 8) / len(drs) * 100), 2) if len(drs) > 0 else 0
            
            results[driver] = {
                "lap_time":              _fmt_timedelta(fastest["LapTime"]),
                "compound":              str(fastest.get("Compound", "Unknown")),
                "max_speed_kmh":         round(float(speeds.max()), 1) if len(speeds) > 0 else None,
                "min_speed_kmh":         round(float(speeds.min()), 1) if len(speeds) > 0 else None,
                "avg_speed_kmh":         round(float(speeds.mean()), 1) if len(speeds) > 0 else None,
                "full_throttle_pct":     round(float(np.sum(throttle >= 98) / len(throttle) * 100), 2) if len(throttle) > 0 else None,
                "off_throttle_pct":      round(float(np.sum(throttle <= 2) / len(throttle) * 100), 2) if len(throttle) > 0 else None,
                "braking_pct":           round(float(np.sum(brake == True) / len(brake) * 100), 2) if len(brake) > 0 else None,
                "gear_distribution":     gear_dist,
                "top_gear_pct":          round(float(gear_dist.get(8, 0) / sum(gear_dist.values()) * 100), 2) if gear_dist else None,
                "drs_active_pct":        drs_active_pct,
                "sector_times": {
                    "s1": _fmt_timedelta(fastest.get("Sector1Time")),
                    "s2": _fmt_timedelta(fastest.get("Sector2Time")),
                    "s3": _fmt_timedelta(fastest.get("Sector3Time")),
                }
            }

        # Delta analysis
        if driver1.upper() in results and driver2.upper() in results:
            d1 = results[driver1.upper()]
            d2 = results[driver2.upper()]
            
            delta_analysis = {}
            if d1.get("max_speed_kmh") and d2.get("max_speed_kmh"):
                delta_analysis["top_speed_delta_kmh"] = round(d1["max_speed_kmh"] - d2["max_speed_kmh"], 1)
            if d1.get("full_throttle_pct") and d2.get("full_throttle_pct"):
                delta_analysis["throttle_delta_pct"] = round(d1["full_throttle_pct"] - d2["full_throttle_pct"], 2)
            if d1.get("braking_pct") and d2.get("braking_pct"):
                delta_analysis["braking_delta_pct"] = round(d1["braking_pct"] - d2["braking_pct"], 2)
        else:
            delta_analysis = {}

        return json.dumps({
            "event":         str(event),
            "year":          year,
            "session":       session_type,
            "comparison":    results,
            "deltas":        delta_analysis,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 4: Tyre Strategy Analysis
# ══════════════════════════════════════════════════════════════════════════════
@tool("analyze_tyre_strategy")
def analyze_tyre_strategy(event: str, year: int = SEASON) -> str:
    """
    Comprehensive tyre strategy analysis: pit stop timing, stint lengths,
    compound choices, tyre degradation rate per driver/compound, 
    undercut/overcut opportunities, virtual safety car impact on strategy.
    Identifies optimal vs actual strategies used.
    """
    try:
        event_key = int(event) if event.isdigit() else event
    except:
        event_key = event

    sess, err = _load_session(year, event_key, "R")
    if err:
        return json.dumps({"error": err})

    try:
        laps = sess.laps.copy()
        laps = laps[laps["LapTime"].notna()]
        laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()

        strategy_data = {}
        for driver in laps["Driver"].unique():
            d_laps = laps[laps["Driver"] == driver].copy().sort_values("LapNumber")
            if d_laps.empty:
                continue

            # Build stints
            stints = []
            if "Compound" in d_laps.columns and "Stint" in d_laps.columns:
                for stint_num, stint_laps in d_laps.groupby("Stint"):
                    if stint_laps.empty:
                        continue
                    times = stint_laps["LapTimeSeconds"].values
                    
                    # Degradation within stint (linear slope)
                    lap_nums = np.arange(len(times))
                    degrad   = float(np.polyfit(lap_nums, times, 1)[0]) if len(times) > 2 else 0.0
                    
                    stints.append({
                        "stint":      int(stint_num),
                        "compound":   str(stint_laps["Compound"].mode()[0]) if not stint_laps["Compound"].mode().empty else "Unknown",
                        "laps":       int(len(stint_laps)),
                        "start_lap":  int(stint_laps["LapNumber"].min()),
                        "end_lap":    int(stint_laps["LapNumber"].max()),
                        "avg_pace_s": round(float(np.nanmean(times)), 3),
                        "degrad_s_per_lap": round(degrad, 4),
                        "best_lap_s": round(float(np.nanmin(times)), 3),
                    })

            strategy_data[driver] = {
                "stints":       stints,
                "num_stops":    max(0, len(stints) - 1),
                "total_laps":   int(len(d_laps)),
                "compounds":    list(set(s["compound"] for s in stints)),
            }

        # Strategy pattern analysis
        stop_counts = {}
        for driver, data in strategy_data.items():
            n = data["num_stops"]
            stop_counts[n] = stop_counts.get(n, 0) + 1
        
        # Most common strategy
        most_common_stops = max(stop_counts, key=stop_counts.get) if stop_counts else 1

        return json.dumps({
            "event":               str(event),
            "year":                year,
            "strategy_by_driver":  strategy_data,
            "stop_count_distribution": stop_counts,
            "most_common_strategy": f"{most_common_stops}-stop",
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 5: Qualifying Analysis
# ══════════════════════════════════════════════════════════════════════════════
@tool("analyze_qualifying_session")
def analyze_qualifying(event: str, year: int = SEASON) -> str:
    """
    Deep qualifying analysis: Q1/Q2/Q3 progression, lap time evolution,
    fastest sectors per driver, track evolution coefficient (how much
    the track improved over the session), fuel-corrected pace estimates,
    and which drivers peaked at the right time.
    """
    try:
        event_key = int(event) if event.isdigit() else event
    except:
        event_key = event

    sess, err = _load_session(year, event_key, "Q")
    if err:
        return json.dumps({"error": err})

    try:
        laps = sess.laps.copy()
        laps = laps[laps["LapTime"].notna()]
        laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()

        driver_results = {}
        for driver in laps["Driver"].unique():
            d_laps = laps[laps["Driver"] == driver].copy()
            
            # Q1/Q2/Q3 best times
            session_bests = {}
            for q_ses in ["Q1", "Q2", "Q3"]:
                q_laps = d_laps[d_laps.get("Session", pd.Series(dtype=str)) == q_ses] if "Session" in d_laps else d_laps
                if not q_laps.empty:
                    session_bests[q_ses] = _fmt_timedelta(q_laps["LapTime"].min())
            
            fastest = d_laps.loc[d_laps["LapTimeSeconds"].idxmin()] if not d_laps.empty else None
            
            # Sector analysis
            sector_data = {}
            for s_col, s_name in [("Sector1Time", "S1"), ("Sector2Time", "S2"), ("Sector3Time", "S3")]:
                if s_col in d_laps.columns:
                    sector_times = d_laps[s_col].dropna()
                    if not sector_times.empty:
                        sector_data[s_name] = {
                            "best":   _fmt_timedelta(sector_times.min()),
                            "mean":   _fmt_timedelta(sector_times.mean()),
                        }

            # Lap improvement across session (how much they found over multiple runs)
            all_times = d_laps["LapTimeSeconds"].sort_values()
            improvement = None
            if len(all_times) >= 2:
                improvement = round(float(all_times.iloc[0] - all_times.iloc[-1]), 3)

            driver_results[driver] = {
                "best_time":      _fmt_timedelta(d_laps["LapTime"].min()) if not d_laps.empty else "N/A",
                "num_laps":       int(len(d_laps)),
                "session_bests":  session_bests,
                "sectors":        sector_data,
                "improvement_s":  improvement,
                "compound":       str(d_laps["Compound"].mode()[0]) if "Compound" in d_laps and not d_laps["Compound"].mode().empty else "Unknown",
            }

        # Grid order
        grid_order = sorted(
            [(d, info["best_time"]) for d, info in driver_results.items() if info["best_time"] != "N/A"],
            key=lambda x: x[1]
        )

        return json.dumps({
            "event":        str(event),
            "year":         year,
            "driver_data":  driver_results,
            "grid_order":   [d for d, _ in grid_order],
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 6: Weather & Track Condition Analysis
# ══════════════════════════════════════════════════════════════════════════════
@tool("analyze_weather_conditions")
def analyze_weather(event: str, session_type: str = "R", year: int = SEASON) -> str:
    """
    Analyze weather conditions during a session: air/track temperature evolution,
    humidity, wind speed/direction, rainfall probability, and how these
    correlate with lap time changes. Identifies weather strategy windows.
    """
    try:
        event_key = int(event) if event.isdigit() else event
    except:
        event_key = event

    sess, err = _load_session(year, event_key, session_type)
    if err:
        return json.dumps({"error": err})

    try:
        weather = sess.weather_data.copy() if sess.weather_data is not None else pd.DataFrame()
        
        if weather.empty:
            return json.dumps({"error": "No weather data available for this session"})

        # Temperature statistics
        air_temp_stats = {
            "min": round(float(weather["AirTemp"].min()), 1) if "AirTemp" in weather else None,
            "max": round(float(weather["AirTemp"].max()), 1) if "AirTemp" in weather else None,
            "mean": round(float(weather["AirTemp"].mean()), 1) if "AirTemp" in weather else None,
        }
        track_temp_stats = {
            "min": round(float(weather["TrackTemp"].min()), 1) if "TrackTemp" in weather else None,
            "max": round(float(weather["TrackTemp"].max()), 1) if "TrackTemp" in weather else None,
            "mean": round(float(weather["TrackTemp"].mean()), 1) if "TrackTemp" in weather else None,
        }

        # Rain
        rain_pct = None
        if "Rainfall" in weather:
            rain_pct = round(float(weather["Rainfall"].mean()) * 100, 1)

        # Wind
        wind_stats = {}
        if "WindSpeed" in weather:
            wind_stats = {
                "max_kmh": round(float(weather["WindSpeed"].max()) * 3.6, 1),
                "avg_kmh": round(float(weather["WindSpeed"].mean()) * 3.6, 1),
            }

        # Track temp vs lap correlation analysis tip
        track_evolution = "No lap data correlation available"
        
        return json.dumps({
            "event":              str(event),
            "session":            session_type,
            "year":               year,
            "air_temp_celsius":   air_temp_stats,
            "track_temp_celsius": track_temp_stats,
            "rain_probability_%": rain_pct,
            "wind":               wind_stats,
            "humidity_mean_%":    round(float(weather["Humidity"].mean()), 1) if "Humidity" in weather else None,
            "data_points":        int(len(weather)),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 7: Driver Performance vs Team Mate
# ══════════════════════════════════════════════════════════════════════════════
@tool("analyze_teammate_performance")
def analyze_teammates(event: str, session_type: str = "R", year: int = SEASON) -> str:
    """
    Head-to-head team mate comparison: identifies who is winning in qualifying
    battle, race pace, tyre management, wet vs dry conditions. Computes
    statistical significance of pace gaps. Perfect for assessing driver form.
    """
    try:
        event_key = int(event) if event.isdigit() else event
    except:
        event_key = event

    sess, err = _load_session(year, event_key, session_type)
    if err:
        return json.dumps({"error": err})

    try:
        # Team groupings from session results
        results = sess.results if hasattr(sess, "results") and sess.results is not None else pd.DataFrame()
        
        # Build team → drivers mapping
        teams = {}
        if not results.empty and "TeamName" in results.columns and "Abbreviation" in results.columns:
            for _, row in results.iterrows():
                team = row["TeamName"]
                drv  = row["Abbreviation"]
                if team not in teams:
                    teams[team] = []
                if drv not in teams[team]:
                    teams[team].append(drv)
        
        if not teams:
            # Fallback: just compare all driver pairs
            return json.dumps({"error": "No team data, try a specific driver comparison tool"})

        laps = sess.laps.copy()
        laps = laps[laps["LapTime"].notna()]
        laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()

        team_battles = {}
        for team, drivers in teams.items():
            if len(drivers) < 2:
                continue
            
            d1, d2 = drivers[0], drivers[1]
            d1_laps = laps[laps["Driver"] == d1]["LapTimeSeconds"]
            d2_laps = laps[laps["Driver"] == d2]["LapTimeSeconds"]
            
            if d1_laps.empty or d2_laps.empty:
                continue

            d1_med = float(d1_laps.median())
            d2_med = float(d2_laps.median())
            gap    = round(d2_med - d1_med, 3)
            winner = d1 if gap > 0 else d2

            team_battles[team] = {
                "driver_1": d1,
                "driver_2": d2,
                "d1_median_pace_s": round(d1_med, 3),
                "d2_median_pace_s": round(d2_med, 3),
                "pace_gap_s": abs(gap),
                "faster_driver": winner,
                "gap_direction": f"{d1} faster by {abs(gap):.3f}s" if gap > 0 else f"{d2} faster by {abs(gap):.3f}s",
            }

        return json.dumps({
            "event":        str(event),
            "session":      session_type,
            "year":         year,
            "team_battles": team_battles,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 8: Sector Time Breakdown
# ══════════════════════════════════════════════════════════════════════════════
@tool("analyze_sector_times")
def analyze_sectors(event: str, session_type: str = "Q", year: int = SEASON) -> str:
    """
    Sector-by-sector analysis: identifies which track sectors each driver
    dominates, theoretical best lap (combining best sectors from any lap),
    and gap between actual and theoretical best. Reveals car characteristics.
    """
    try:
        event_key = int(event) if event.isdigit() else event
    except:
        event_key = event

    sess, err = _load_session(year, event_key, session_type)
    if err:
        return json.dumps({"error": err})

    try:
        laps = sess.laps.copy()
        laps = laps[laps["LapTime"].notna()]

        sector_analysis = {}
        theoretical_bests = {}

        for driver in laps["Driver"].unique():
            d_laps = laps[laps["Driver"] == driver]
            
            s1_best = d_laps["Sector1Time"].min() if "Sector1Time" in d_laps else pd.NaT
            s2_best = d_laps["Sector2Time"].min() if "Sector2Time" in d_laps else pd.NaT
            s3_best = d_laps["Sector3Time"].min() if "Sector3Time" in d_laps else pd.NaT
            
            if not pd.isna(s1_best) and not pd.isna(s2_best) and not pd.isna(s3_best):
                theoretical = s1_best + s2_best + s3_best
                actual_best  = d_laps["LapTime"].min()
                gap_to_theo  = (actual_best - theoretical).total_seconds() if not pd.isna(actual_best) else None
                
                sector_analysis[driver] = {
                    "S1_best": _fmt_timedelta(s1_best),
                    "S2_best": _fmt_timedelta(s2_best),
                    "S3_best": _fmt_timedelta(s3_best),
                    "theoretical_best": _fmt_timedelta(theoretical),
                    "actual_best":      _fmt_timedelta(actual_best),
                    "gap_to_theoretical_s": round(gap_to_theo, 3) if gap_to_theo else None,
                }
                theoretical_bests[driver] = theoretical.total_seconds() if theoretical else 999

        # Theoretical ranking
        theo_ranking = sorted(theoretical_bests.items(), key=lambda x: x[1])

        # Sector dominance: who is best in each sector
        sector_winners = {}
        for sector_key, sector_name in [("S1_best", "Sector 1"), ("S2_best", "Sector 2"), ("S3_best", "Sector 3")]:
            best_driver = None
            best_time   = "99:99.999"
            for driver, data in sector_analysis.items():
                t = data.get(sector_key, "99:99.999")
                if t != "N/A" and t < best_time:
                    best_time   = t
                    best_driver = driver
            sector_winners[sector_name] = {"driver": best_driver, "time": best_time}

        return json.dumps({
            "event":             str(event),
            "session":           session_type,
            "year":              year,
            "sector_analysis":   sector_analysis,
            "sector_dominance":  sector_winners,
            "theoretical_ranking": [d for d, _ in theo_ranking],
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 9: Car Speed & Power Unit Analysis
# ══════════════════════════════════════════════════════════════════════════════
@tool("analyze_car_performance")
def analyze_car_performance(event: str, session_type: str = "Q", year: int = SEASON) -> str:
    """
    Analyzes straight-line speed, power unit performance, and aerodynamic
    efficiency. Computes: speed trap rankings, avg speed on straights vs corners,
    speed under DRS, acceleration profiles, and engine deployment patterns.
    Reveals which teams have power unit or aero advantage.
    """
    try:
        event_key = int(event) if event.isdigit() else event
    except:
        event_key = event

    sess, err = _load_session(year, event_key, session_type)
    if err:
        return json.dumps({"error": err})

    try:
        laps = sess.laps.copy()
        laps = laps[laps["LapTime"].notna()]

        car_perf = {}
        for driver in laps["Driver"].unique():
            try:
                fastest = laps[laps["Driver"] == driver].pick_fastest()
                tel     = fastest.get_car_data().add_distance()
                
                speeds  = tel["Speed"].values
                gears   = tel["nGear"].values if "nGear" in tel else np.array([])
                drs     = tel["DRS"].values   if "DRS" in tel   else np.array([])
                
                # High speed zones (speed > 280 kmh)
                high_speed_mask  = speeds > 280
                # Low speed zones (cornering, speed < 150 kmh)
                low_speed_mask   = speeds < 150
                
                # DRS speed boost
                drs_active_mask  = drs > 8
                drs_inactive_mask = (drs <= 8) & (speeds > 250)
                
                drs_speed_boost = None
                if drs_active_mask.any() and drs_inactive_mask.any():
                    drs_speed_boost = round(
                        float(speeds[drs_active_mask].mean() - speeds[drs_inactive_mask].mean()), 1
                    )

                # Acceleration: identify acceleration phases
                speed_diff = np.diff(speeds)
                accel_mask = speed_diff > 0.5
                max_accel  = round(float(speed_diff[accel_mask].max()), 2) if accel_mask.any() else None

                car_perf[driver] = {
                    "top_speed_kmh":          round(float(speeds.max()), 1),
                    "avg_high_speed_zone_kmh": round(float(speeds[high_speed_mask].mean()), 1) if high_speed_mask.any() else None,
                    "avg_corner_speed_kmh":    round(float(speeds[low_speed_mask].mean()), 1)  if low_speed_mask.any() else None,
                    "drs_speed_boost_kmh":     drs_speed_boost,
                    "drs_usage_pct":           round(float(np.sum(drs_active_mask) / len(speeds) * 100), 1) if len(speeds) > 0 else 0,
                    "max_acceleration_delta":  max_accel,
                    "top_gear_speed_kmh":      round(float(speeds[gears == 8].mean()), 1) if (len(gears) > 0 and np.any(gears == 8)) else None,
                }
            except Exception:
                car_perf[driver] = {"error": "Telemetry not available"}

        # Rankings
        top_speed_ranking = sorted(
            [(d, info.get("top_speed_kmh", 0)) for d, info in car_perf.items() if isinstance(info.get("top_speed_kmh"), (int, float))],
            key=lambda x: x[1], reverse=True
        )

        return json.dumps({
            "event":             str(event),
            "session":           session_type,
            "year":              year,
            "car_performance":   car_perf,
            "top_speed_ranking": [{"driver": d, "speed": s} for d, s in top_speed_ranking],
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 10: Championship Standings & Points Analysis
# ══════════════════════════════════════════════════════════════════════════════
@tool("get_championship_standings")
def get_championship_standings(year: int = SEASON) -> str:
    """
    Retrieve current F1 Driver and Constructor Championship standings.
    Computes: points gaps, championship scenarios, average points per race,
    win rate, podium rate, DNF analysis, and championship trajectory.
    Useful for predicting championship outcomes.
    """
    try:
        results_data = {"drivers": {}, "constructors": {}}
        
        schedule  = fastf1.get_event_schedule(year)
        now       = pd.Timestamp.now(tz="UTC")
        past_events = schedule[schedule["Session5Date"] < now]
        
        all_driver_points    = {}
        all_constructor_points = {}
        race_count           = 0
        
        for _, event_row in past_events.iterrows():
            try:
                sess, err = _load_session(year, int(event_row["RoundNumber"]), "R")
                if err or sess is None:
                    continue
                
                if sess.results is None or sess.results.empty:
                    continue
                
                race_count += 1
                
                # F1 points system
                POINTS = {1:25, 2:18, 3:15, 4:12, 5:10, 6:8, 7:6, 8:4, 9:2, 10:1}
                FL_POINT = 1  # fastest lap bonus (simplified)
                
                for _, res in sess.results.iterrows():
                    pos    = int(res.get("Position", 99)) if not pd.isna(res.get("Position", np.nan)) else 99
                    driver = str(res.get("Abbreviation", "UNK"))
                    team   = str(res.get("TeamName", "Unknown"))
                    pts    = POINTS.get(pos, 0)
                    
                    if driver not in all_driver_points:
                        all_driver_points[driver] = {"points": 0, "team": team, "wins": 0, "podiums": 0, "dnfs": 0}
                    
                    all_driver_points[driver]["points"] += pts
                    if pos == 1:
                        all_driver_points[driver]["wins"] += 1
                    if pos <= 3:
                        all_driver_points[driver]["podiums"] += 1
                    
                    status = str(res.get("Status", ""))
                    if "Retired" in status or "Accident" in status or "DNF" in status:
                        all_driver_points[driver]["dnfs"] += 1
                    
                    if team not in all_constructor_points:
                        all_constructor_points[team] = 0
                    all_constructor_points[team] += pts
                    
            except Exception:
                continue
        
        # Sort standings
        driver_standings = sorted(
            all_driver_points.items(), key=lambda x: x[1]["points"], reverse=True
        )
        constructor_standings = sorted(
            all_constructor_points.items(), key=lambda x: x[1], reverse=True
        )
        
        # Compute gaps
        leader_pts = driver_standings[0][1]["points"] if driver_standings else 0
        driver_ranking = []
        for pos, (driver, data) in enumerate(driver_standings, 1):
            driver_ranking.append({
                "position":    pos,
                "driver":      driver,
                "team":        data["team"],
                "points":      data["points"],
                "gap_to_leader": leader_pts - data["points"],
                "wins":        data["wins"],
                "podiums":     data["podiums"],
                "dnfs":        data["dnfs"],
                "avg_pts_per_race": round(data["points"] / race_count, 2) if race_count > 0 else 0,
            })
        
        return json.dumps({
            "year":                 year,
            "races_completed":      race_count,
            "driver_standings":     driver_ranking[:20],
            "constructor_standings": [{"position": i+1, "team": t, "points": p}
                                      for i, (t, p) in enumerate(constructor_standings)],
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 11: Python Code Execution (Math & Custom Analysis)
# ══════════════════════════════════════════════════════════════════════════════
@tool("execute_python_analysis")
def execute_python_analysis(code: str, description: str = "") -> str:
    """
    Execute custom Python code for advanced F1 mathematical analysis.
    Has access to: numpy, pandas, scipy, matplotlib, fastf1.
    The code should print() its results. Returns stdout output.
    Use this for: regression analysis, statistical tests, custom metrics,
    Fourier analysis of lap times, correlation matrices, probability modeling.
    
    Example code:
    ```
    import numpy as np
    lap_times = [91.2, 91.5, 91.8, 92.1]
    degradation = np.polyfit(range(len(lap_times)), lap_times, 1)[0]
    print(f"Degradation rate: {degradation:.3f} s/lap")
    ```
    """
    import io
    import sys
    import traceback
    
    # Safe execution environment - pre-import common libraries
    import builtins
    safe_globals = {
        "__builtins__": builtins,
        "np":      __import__("numpy"),
        "pd":      __import__("pandas"),
        "scipy":   __import__("scipy"),
        "math":    __import__("math"),
        "json":    __import__("json"),
        "fastf1":  fastf1,
        "SEASON":  SEASON,
    }
    
    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    
    try:
        exec(code, safe_globals)
        output = buffer.getvalue()
        return json.dumps({
            "description": description,
            "status":      "success",
            "output":      output[:5000],  # limit output
        })
    except Exception as e:
        return json.dumps({
            "description": description,
            "status":      "error",
            "error":       str(e),
            "traceback":   traceback.format_exc()[:2000],
        })
    finally:
        sys.stdout = old_stdout


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 12: Statistical Pattern Detection
# ══════════════════════════════════════════════════════════════════════════════
@tool("detect_statistical_patterns")
def detect_statistical_patterns(event: str, session_type: str = "R", 
                                  year: int = SEASON) -> str:
    """
    Advanced statistical analysis: detects non-obvious patterns in F1 data.
    Includes: lap time autocorrelation (car balance changes), 
    performance outlier detection (exceptional/bad laps), 
    driver consistency index, stint performance curves,
    correlation between track position and lap pace.
    Surfaces patterns humans might miss in raw data.
    """
    try:
        event_key = int(event) if event.isdigit() else event
    except:
        event_key = event

    sess, err = _load_session(year, event_key, session_type)
    if err:
        return json.dumps({"error": err})

    try:
        laps = sess.laps.copy()
        laps = laps[laps["LapTime"].notna()]
        laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()

        patterns = {}

        for driver in laps["Driver"].unique():
            d_laps = laps[laps["Driver"] == driver].copy().sort_values("LapNumber")
            if len(d_laps) < 8:
                continue
            
            times = d_laps["LapTimeSeconds"].values
            
            # 1. Outlier detection (> 2 std devs from mean = outlier lap)
            mean_t    = np.mean(times)
            std_t     = np.std(times)
            outliers  = np.where(np.abs(times - mean_t) > 2 * std_t)[0]
            
            # 2. Autocorrelation at lag 1 (do slow laps follow slow laps?)
            lag1_corr = float(np.corrcoef(times[:-1], times[1:])[0, 1]) if len(times) > 4 else 0

            # 3. Consistency score: lower is better (IQR-based)
            iqr = float(np.percentile(times, 75) - np.percentile(times, 25))
            
            # 4. "Purple Lap" frequency: laps within 0.5s of fastest
            fastest_lap = times.min()
            purple_laps = int(np.sum(times <= fastest_lap + 0.5))
            
            # 5. Second half vs first half pace
            mid = len(times) // 2
            h1_mean = float(np.mean(times[:mid])) if mid > 0 else 0
            h2_mean = float(np.mean(times[mid:])) if len(times) - mid > 0 else 0
            pace_delta_2nd_half = round(h2_mean - h1_mean, 3)
            
            # 6. Trend detection
            if len(times) > 5:
                overall_slope = float(np.polyfit(np.arange(len(times)), times, 1)[0])
            else:
                overall_slope = 0

            patterns[driver] = {
                "outlier_laps":          [int(d_laps.iloc[i]["LapNumber"]) for i in outliers],
                "outlier_count":         int(len(outliers)),
                "lag1_autocorrelation":  round(lag1_corr, 4),
                "iqr_consistency_s":     round(iqr, 4),
                "purple_lap_count":      purple_laps,
                "2nd_half_pace_delta_s": pace_delta_2nd_half,
                "overall_trend_s_per_lap": round(overall_slope, 4),
                "interpretation": {
                    "consistent":  iqr < 0.5,
                    "improving":   overall_slope < -0.05,
                    "degrading":   overall_slope > 0.1,
                    "correlated":  abs(lag1_corr) > 0.5,
                }
            }

        return json.dumps({
            "event":    str(event),
            "session":  session_type,
            "year":     year,
            "patterns": patterns,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# Evidence Tools: deterministic summaries for small-model synthesis
# ══════════════════════════════════════════════════════════════════════════════
@tool("build_race_pace_evidence")
def build_race_pace_evidence(event: str, year: int = SEASON) -> str:
    """
    Build a compact, evidence-first race pace packet for LLM synthesis.
    Saves full raw telemetry/statistical outputs as an artifact and returns
    only the highest-value metrics, rankings, and anomalies.
    """
    lap_raw = _safe_json_loads(_call_tool_func(analyze_lap_times, event=event, session_type="R", year=year))
    pattern_raw = _safe_json_loads(_call_tool_func(detect_statistical_patterns, event=event, session_type="R", year=year))
    if lap_raw.get("error"):
        return json.dumps(lap_raw, indent=2)
    if pattern_raw.get("error"):
        return json.dumps(pattern_raw, indent=2)

    drivers = lap_raw.get("drivers", {})
    patterns = pattern_raw.get("patterns", {})
    ranking = lap_raw.get("pace_ranking", [])
    gaps = lap_raw.get("gaps_to_leader", {})

    top_pace = []
    for driver in ranking[:5]:
        info = drivers.get(driver, {})
        top_pace.append({
            "driver": driver,
            "gap_to_leader": gaps.get(driver),
            "median_lap": info.get("median_lap"),
            "mean_lap_seconds": info.get("mean_lap_seconds"),
            "consistency_cv_%": info.get("consistency_cv_%"),
            "pace_degr_s_per_lap": info.get("pace_degr_s_per_lap"),
        })

    degradation = sorted(
        [
            {
                "driver": d,
                "pace_degr_s_per_lap": info.get("pace_degr_s_per_lap"),
                "compound_count": len(info.get("compounds_used", [])),
            }
            for d, info in drivers.items()
            if isinstance(info.get("pace_degr_s_per_lap"), (int, float))
        ],
        key=lambda item: item["pace_degr_s_per_lap"],
        reverse=True,
    )

    purple_counts = sorted(
        [
            {"driver": d, "purple_lap_count": p.get("purple_lap_count", 0)}
            for d, p in patterns.items()
        ],
        key=lambda item: item["purple_lap_count"],
        reverse=True,
    )

    anomalies = sorted(
        [
            {
                "driver": d,
                "lag1_autocorrelation": p.get("lag1_autocorrelation"),
                "outlier_count": p.get("outlier_count"),
                "2nd_half_pace_delta_s": p.get("2nd_half_pace_delta_s"),
            }
            for d, p in patterns.items()
            if abs(float(p.get("lag1_autocorrelation", 0) or 0)) >= 0.45 or int(p.get("outlier_count", 0) or 0) >= 2
        ],
        key=lambda item: (abs(item.get("lag1_autocorrelation") or 0), item.get("outlier_count") or 0),
        reverse=True,
    )

    findings = []
    if top_pace:
        leader = top_pace[0]
        findings.append(
            f"{leader['driver']} leads race-trim pace at {leader.get('mean_lap_seconds')}s average with {leader.get('consistency_cv_%')}% CV."
        )
    if degradation:
        findings.append(
            f"Highest degradation observed: {degradation[0]['driver']} at {degradation[0]['pace_degr_s_per_lap']} s/lap."
        )
    if purple_counts:
        findings.append(
            f"Most near-fastest laps: {purple_counts[0]['driver']} with {purple_counts[0]['purple_lap_count']} purple laps."
        )
    if anomalies:
        findings.append(
            f"Strongest anomaly signal: {anomalies[0]['driver']} autocorrelation={anomalies[0]['lag1_autocorrelation']}, outliers={anomalies[0]['outlier_count']}."
        )

    raw_artifact = {
        "lap_time_analysis": lap_raw,
        "statistical_patterns": pattern_raw,
    }
    artifact_path = _write_tool_artifact("race_pace_evidence", raw_artifact)

    return json.dumps({
        "event": str(event),
        "year": year,
        "schema": "telemetry_race_pace_evidence",
        "artifact_path": artifact_path,
        "top_pace": top_pace,
        "highest_degradation": degradation[:5],
        "purple_lap_leaders": purple_counts[:5],
        "notable_anomalies": anomalies[:5],
        "findings": findings,
    }, indent=2)


@tool("build_qualifying_evidence")
def build_qualifying_evidence(event: str, year: int = SEASON) -> str:
    """
    Build a compact qualifying evidence packet with deterministic rankings,
    sector dominance, theoretical-vs-actual gaps, and speed-trap context.
    """
    quali_raw = _safe_json_loads(_call_tool_func(analyze_qualifying, event=event, year=year))
    sector_raw = _safe_json_loads(_call_tool_func(analyze_sectors, event=event, session_type="Q", year=year))
    car_raw = _safe_json_loads(_call_tool_func(analyze_car_performance, event=event, session_type="Q", year=year))
    for payload in (quali_raw, sector_raw, car_raw):
        if payload.get("error"):
            return json.dumps(payload, indent=2)

    driver_data = quali_raw.get("driver_data", {})
    sector_data = sector_raw.get("sector_analysis", {})
    grid_order = quali_raw.get("grid_order", [])
    top_speed = car_raw.get("top_speed_ranking", [])

    grid_top = []
    for pos, driver in enumerate(grid_order[:5], 1):
        info = driver_data.get(driver, {})
        gap_to_theoretical = sector_data.get(driver, {}).get("gap_to_theoretical_s")
        improvement = info.get("improvement_s")
        grid_top.append({
            "position": pos,
            "driver": driver,
            "best_time": info.get("best_time"),
            "improvement_s": abs(improvement) if isinstance(improvement, (int, float)) else improvement,
            "gap_to_theoretical_s": gap_to_theoretical,
            "compound": info.get("compound"),
        })

    sector_dominance = sector_raw.get("sector_dominance", {})
    theoretical_left = sorted(
        [
            {
                "driver": driver,
                "gap_to_theoretical_s": info.get("gap_to_theoretical_s"),
            }
            for driver, info in sector_data.items()
            if isinstance(info.get("gap_to_theoretical_s"), (int, float))
        ],
        key=lambda item: item["gap_to_theoretical_s"],
        reverse=True,
    )

    findings = []
    if grid_top:
        pole = grid_top[0]
        findings.append(
            f"{pole['driver']} leads qualifying on {pole['best_time']} with {pole.get('gap_to_theoretical_s')}s left to theoretical best."
        )
    for sector_name, winner in sector_dominance.items():
        if winner.get("driver"):
            findings.append(f"{sector_name} benchmark: {winner['driver']} ({winner.get('time')}).")
    if top_speed:
        findings.append(f"Top straight-line speed: {top_speed[0]['driver']} at {top_speed[0]['speed']} km/h.")

    raw_artifact = {
        "qualifying_analysis": quali_raw,
        "sector_analysis": sector_raw,
        "car_performance": car_raw,
    }
    artifact_path = _write_tool_artifact("qualifying_evidence", raw_artifact)

    return json.dumps({
        "event": str(event),
        "year": year,
        "schema": "telemetry_qualifying_evidence",
        "artifact_path": artifact_path,
        "grid_top": grid_top,
        "sector_dominance": sector_dominance,
        "theoretical_time_left": theoretical_left[:5],
        "top_speed_ranking": top_speed[:5],
        "findings": findings[:8],
    }, indent=2)


@tool("build_driver_battle_evidence")
def build_driver_battle_evidence(event: str, year: int = SEASON) -> str:
    """
    Build a compact driver-battle evidence packet focused on the top teams.
    Computes qualifying and race team-mate gaps, per-sector winners, and a
    deterministic qualifying-vs-race gap correlation summary.
    """
    try:
        event_key = int(event) if str(event).isdigit() else event
    except Exception:
        event_key = event

    sess, err = _load_session(year, event_key, "Q")
    if err:
        return json.dumps({"error": err}, indent=2)

    q_tm_raw = _safe_json_loads(_call_tool_func(analyze_teammates, event=event, session_type="Q", year=year))
    r_tm_raw = _safe_json_loads(_call_tool_func(analyze_teammates, event=event, session_type="R", year=year))
    if q_tm_raw.get("error"):
        return json.dumps(q_tm_raw, indent=2)
    if r_tm_raw.get("error"):
        return json.dumps(r_tm_raw, indent=2)

    results = sess.results if hasattr(sess, "results") and sess.results is not None else pd.DataFrame()
    ordered_teams = []
    if not results.empty and "TeamName" in results.columns:
        seen = set()
        for _, row in results.sort_values("Position").iterrows():
            team = str(row.get("TeamName", ""))
            if team and team not in seen:
                ordered_teams.append(team)
                seen.add(team)
            if len(ordered_teams) >= 4:
                break

    q_battles = q_tm_raw.get("team_battles", {})
    r_battles = r_tm_raw.get("team_battles", {})
    selected_teams = [team for team in ordered_teams if team in q_battles][:4] or list(q_battles.keys())[:4]

    battle_cards = []
    qual_gaps = []
    race_gaps = []
    detailed_raw = {}

    for team in selected_teams:
        q_info = q_battles.get(team, {})
        r_info = r_battles.get(team, {})
        d1 = q_info.get("driver_1")
        d2 = q_info.get("driver_2")
        if not d1 or not d2:
            continue

        compare_raw = _safe_json_loads(
            _call_tool_func(compare_driver_telemetry, event=event, driver1=d1, driver2=d2, session_type="Q", year=year)
        )
        detailed_raw[team] = compare_raw
        comparison = compare_raw.get("comparison", {})
        d1_info = comparison.get(d1, {})
        d2_info = comparison.get(d2, {})

        sector_wins = {}
        for key in ("s1", "s2", "s3"):
            t1 = d1_info.get("sector_times", {}).get(key)
            t2 = d2_info.get("sector_times", {}).get(key)
            if t1 and t2 and t1 != "N/A" and t2 != "N/A":
                sector_wins[key] = d1 if t1 < t2 else d2

        q_gap = q_info.get("pace_gap_s")
        r_gap = r_info.get("pace_gap_s")
        if isinstance(q_gap, (int, float)) and isinstance(r_gap, (int, float)):
            qual_gaps.append(float(q_gap))
            race_gaps.append(float(r_gap))

        battle_cards.append({
            "team": team,
            "driver_1": d1,
            "driver_2": d2,
            "qualifying_faster_driver": q_info.get("faster_driver"),
            "qualifying_gap_s": q_gap,
            "race_faster_driver": r_info.get("faster_driver"),
            "race_gap_s": r_gap,
            "top_speed_delta_kmh": compare_raw.get("deltas", {}).get("top_speed_delta_kmh"),
            "throttle_delta_pct": compare_raw.get("deltas", {}).get("throttle_delta_pct"),
            "sector_wins": sector_wins,
        })

    correlation = None
    if len(qual_gaps) >= 2 and len(race_gaps) >= 2:
        correlation = round(float(np.corrcoef(qual_gaps, race_gaps)[0, 1]), 4)

    findings = []
    if battle_cards:
        closest = min(
            [card for card in battle_cards if isinstance(card.get("qualifying_gap_s"), (int, float))],
            key=lambda item: item["qualifying_gap_s"],
            default=None,
        )
        widest = max(
            [card for card in battle_cards if isinstance(card.get("qualifying_gap_s"), (int, float))],
            key=lambda item: item["qualifying_gap_s"],
            default=None,
        )
        if closest:
            findings.append(
                f"Closest qualifying battle: {closest['team']} at {closest['qualifying_gap_s']}s."
            )
        if widest:
            findings.append(
                f"Widest qualifying battle: {widest['team']} at {widest['qualifying_gap_s']}s."
            )
    if correlation is not None:
        findings.append(f"Qualifying-vs-race team-mate gap correlation: {correlation}.")

    raw_artifact = {
        "qualifying_teammates": q_tm_raw,
        "race_teammates": r_tm_raw,
        "detailed_comparisons": detailed_raw,
    }
    artifact_path = _write_tool_artifact("driver_battle_evidence", raw_artifact)

    return json.dumps({
        "event": str(event),
        "year": year,
        "schema": "telemetry_driver_battle_evidence",
        "artifact_path": artifact_path,
        "battle_cards": battle_cards,
        "qualifying_race_gap_correlation": correlation,
        "findings": findings,
    }, indent=2)


# Export all tools for use in agents
ALL_TELEMETRY_TOOLS = [
    get_season_schedule,
    analyze_lap_times,
    compare_driver_telemetry,
    analyze_tyre_strategy,
    analyze_qualifying,
    analyze_weather,
    analyze_teammates,
    analyze_sectors,
    analyze_car_performance,
    get_championship_standings,
    execute_python_analysis,
    detect_statistical_patterns,
    build_race_pace_evidence,
    build_qualifying_evidence,
    build_driver_battle_evidence,
]


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 13: Circuit Profile Analysis
# ══════════════════════════════════════════════════════════════════════════════
@tool("get_circuit_profile")
def get_circuit_profile(circuit_name: str) -> str:
    """
    Get detailed circuit profile: downforce level, tyre demands, overtaking
    opportunities, key corners, and which car/driver traits are most important.
    Useful for pre-race analysis and understanding why certain teams perform well.
    Input: circuit_name as string (e.g. 'Monaco', 'Silverstone', 'Monza', 'Spa')
    """
    try:
        from tools.f1_static_data import get_circuit_profile, CIRCUIT_PROFILES
        profile = get_circuit_profile(circuit_name)
        # Also include list of all available circuit profiles
        available = list(CIRCUIT_PROFILES.keys())
        return json.dumps({
            "queried": circuit_name,
            "profile": profile,
            "all_circuits_in_db": available,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 14: Driver & Team Lineup Info
# ══════════════════════════════════════════════════════════════════════════════
@tool("get_driver_lineup")
def get_driver_lineup(year: int = SEASON) -> str:
    """
    Get the full driver and team lineup for a given F1 season.
    Returns: driver codes, full names, team assignments, car numbers.
    Input: year as integer (e.g. 2026)
    """
    try:
        from tools.f1_static_data import get_drivers
        drivers = get_drivers(int(year))
        # Organize by team
        teams = {}
        for code, info in drivers.items():
            team = info["team"]
            if team not in teams:
                teams[team] = []
            teams[team].append({"code": code, **info})
        return json.dumps({
            "year": year,
            "drivers": drivers,
            "by_team": teams,
            "total_drivers": len(drivers),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# Add new tools to the export list
ALL_TELEMETRY_TOOLS.extend([get_circuit_profile, get_driver_lineup])
