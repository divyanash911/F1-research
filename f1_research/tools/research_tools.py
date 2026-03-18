"""
F1 Research Program - News & Web Research Tools
Tools for fetching, parsing, and analyzing F1 news and current information.
"""

import json
import os
import re
import time
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from crewai.tools import tool

NEWS_CACHE_DIR = Path("news_cache")
NEWS_CACHE_DIR.mkdir(exist_ok=True)


def _truncate_text(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _cache_key(query: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", query.lower())[:50]


def _is_fresh(filepath: Path, hours: int = 2) -> bool:
    if not filepath.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(filepath.stat().st_mtime)
    return age < timedelta(hours=hours)


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 1: F1 News Search
# ══════════════════════════════════════════════════════════════════════════════
@tool("search_f1_latest_news")
def search_f1_news(query: str, max_results: int) -> str:
    """
    Search for the latest F1 news articles. Provide specific queries like:
    'F1 2026 Bahrain Grand Prix results', 'Ferrari car upgrade', 
    'Hamilton Mercedes contract', 'FIA regulation change 2026'.
    Returns: article titles, summaries, sources, and publication dates.
    """
    # Defensive defaults: the tool schema requires max_results, but we still
    # keep runtime behavior safe if a caller passes something odd.
    if not query or not str(query).strip():
        query = "latest Formula 1 news"
    try:
        max_results = int(max_results)
    except Exception:
        max_results = 8
    max_results = max(1, min(max_results, 5))

    cache_file = NEWS_CACHE_DIR / f"{_cache_key(query)}.json"
    
    if _is_fresh(cache_file, hours=1):
        with open(cache_file) as f:
            return f.read()

    try:
        from duckduckgo_search import DDGS
        
        results = []
        with DDGS() as ddgs:
            f1_query = f"Formula 1 F1 {query} 2026"
            news_results = list(ddgs.news(f1_query, max_results=max_results))
            
            for item in news_results:
                results.append({
                    "title":   _truncate_text(item.get("title", ""), 120),
                    "url":     item.get("url", ""),
                    "source":  item.get("source", ""),
                    "date":    item.get("date", ""),
                    "summary": _truncate_text(item.get("body", ""), 180),
                })
        
        output = json.dumps({
            "query":   query,
            "count":   len(results),
            "results": results,
            "fetched": datetime.now().isoformat(),
        }, indent=2)
        
        with open(cache_file, "w") as f:
            f.write(output)
        
        return output
    except Exception as e:
        return json.dumps({"error": str(e), "query": query})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 2: F1 Web Search (general facts)
# ══════════════════════════════════════════════════════════════════════════════
@tool("search_f1_facts")
def search_f1_facts(query: str) -> str:
    """
    Search for F1 historical facts, statistics, records, and general information.
    Great for: circuit characteristics, historical race data, driver records,
    team histories, technical regulations, car specifications.
    Examples: 'Monaco GP historical winners', 'F1 fastest lap record',
    'Red Bull RB20 car specifications', 'Verstappen career statistics'.
    """
    cache_file = NEWS_CACHE_DIR / f"facts_{_cache_key(query)}.json"
    
    if _is_fresh(cache_file, hours=24):
        with open(cache_file) as f:
            return f.read()

    try:
        from duckduckgo_search import DDGS
        
        results = []
        with DDGS() as ddgs:
            search_results = list(ddgs.text(f"F1 Formula 1 {query}", max_results=4))
            
            for item in search_results:
                results.append({
                    "title":   _truncate_text(item.get("title", ""), 120),
                    "url":     item.get("href", ""),
                    "content": _truncate_text(item.get("body", ""), 220),
                })
        
        output = json.dumps({
            "query":   query,
            "count":   len(results),
            "results": results,
        }, indent=2)
        
        with open(cache_file, "w") as f:
            f.write(output)
        
        return output
    except Exception as e:
        return json.dumps({"error": str(e), "query": query})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 3: Save Insight/Report
# ══════════════════════════════════════════════════════════════════════════════
@tool("publish_f1_insight")
def publish_insight(
    title: str,
    insight_type: str,
    content: str,
    confidence: float = 0.75,
    tags: str = ""
) -> str:
    """
    Publish a research insight or finding to the insights repository.
    This permanently saves the finding for human review and future reference.
    insight_type: 'telemetry_finding' | 'race_prediction' | 'trend_analysis' |
                  'strategy_insight' | 'driver_analysis' | 'championship_outlook' |
                  'technical_discovery' | 'statistical_anomaly'
    confidence: 0.0 to 1.0 (your confidence in this finding)
    tags: comma-separated tags e.g. "VER, Red Bull, lap time, 2026"
    """
    try:
        insights_dir = Path("insights")
        insights_dir.mkdir(exist_ok=True)
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H:%M:%S")
        fname    = insights_dir / f"{date_str}_{insight_type.lower().replace(' ', '_')}.md"
        
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        
        entry = f"""
---
## {title}
**Type:** {insight_type}  
**Confidence:** {confidence:.0%}  
**Published:** {date_str} {time_str}  
**Tags:** {', '.join(tag_list)}

{content}

"""
        with open(fname, "a", encoding="utf-8") as f:
            # Add header if new file
            if fname.stat().st_size == 0:
                f.write(f"# F1 Autonomous Research Insights — {date_str}\n\n")
            f.write(entry)
        
        return json.dumps({
            "status":    "published",
            "file":      str(fname),
            "title":     title,
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 4: Read Previously Published Insights
# ══════════════════════════════════════════════════════════════════════════════
@tool("read_published_insights")
def read_published_insights(date_filter: str = "today", max_chars: int = 1800) -> str:
    """
    Read previously published F1 research insights. Use this to avoid
    duplicating research and to build on prior findings.
    date_filter: 'today' | 'this_week' | 'all' | specific date 'YYYY-MM-DD'
    """
    try:
        insights_dir = Path("insights")
        if not insights_dir.exists():
            return json.dumps({"status": "no_insights", "message": "No insights published yet"})
        
        now       = datetime.now()
        all_files = sorted(insights_dir.glob("*.md"), reverse=True)
        
        selected = []
        for f in all_files:
            if date_filter == "today":
                if f.name.startswith(now.strftime("%Y-%m-%d")):
                    selected.append(f)
            elif date_filter == "this_week":
                week_ago = now - timedelta(days=7)
                file_date = datetime.strptime(f.name[:10], "%Y-%m-%d")
                if file_date >= week_ago:
                    selected.append(f)
            elif date_filter == "all":
                selected.append(f)
            else:
                if f.name.startswith(date_filter):
                    selected.append(f)
        
        combined = ""
        for f in selected[:5]:  # limit to 5 files
            combined += f.read_text(encoding="utf-8")
        
        if not combined:
            return json.dumps({"status": "empty", "message": "No insights found for filter"})
        
        return json.dumps({
            "filter":       date_filter,
            "files_found":  len(selected),
            "content":      combined[:max_chars],
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 5: F1 Calendar & Next Race Info
# ══════════════════════════════════════════════════════════════════════════════
@tool("get_next_race_info")
def get_next_race_info() -> str:
    """
    Get information about the upcoming F1 race including:
    circuit name, location, date, historical data about the circuit,
    recent results at this track, and key strategic considerations.
    """
    try:
        import fastf1
        from datetime import timezone
        
        import pandas as pd
        year     = int(os.getenv("F1_SEASON", "2026"))
        schedule = fastf1.get_event_schedule(year)
        now      = pd.Timestamp.now(tz="UTC")
        
        upcoming = schedule[schedule["Session5Date"] > now].sort_values("Session5Date")
        
        if upcoming.empty:
            return json.dumps({"message": "No upcoming races in current season"})
        
        next_race = upcoming.iloc[0]
        days_away = int((next_race["Session5Date"] - now).days)
        
        return json.dumps({
            "next_race": {
                "name":         next_race["EventName"],
                "round":        int(next_race["RoundNumber"]),
                "circuit":      next_race.get("Location", "Unknown"),
                "country":      next_race["Country"],
                "race_date":    str(next_race["Session5Date"])[:10],
                "days_away":    days_away,
                "fp1_date":     str(next_race.get("Session1Date", "N/A"))[:10],
                "fp2_date":     str(next_race.get("Session2Date", "N/A"))[:10],
                "fp3_date":     str(next_race.get("Session3Date", "N/A"))[:10],
                "quali_date":   str(next_race.get("Session4Date", "N/A"))[:10],
            },
            "remaining_races": int(len(upcoming)),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


import pandas as pd  # ensure available

ALL_RESEARCH_TOOLS = [
    search_f1_news,
    search_f1_facts,
    publish_insight,
    read_published_insights,
    get_next_race_info,
]
