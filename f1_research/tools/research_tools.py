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

MODULE_ROOT = Path(__file__).resolve().parent.parent


def _select_runtime_dir(dirname: str) -> Path:
    cwd_candidate = Path(dirname)
    module_candidate = MODULE_ROOT / dirname
    candidates = [cwd_candidate, module_candidate]

    def score(path: Path) -> tuple[int, int, int]:
        exists = int(path.exists())
        markdown_count = len(list(path.glob("*.md"))) if path.exists() else 0
        size = sum(item.stat().st_size for item in path.glob("*.md")) if path.exists() else 0
        return (markdown_count, size, exists)

    return max(candidates, key=score)


def _get_news_cache_dir() -> Path:
    path = _select_runtime_dir("news_cache")
    path.mkdir(exist_ok=True)
    return path


def _get_insights_dir() -> Path:
    path = _select_runtime_dir("insights")
    path.mkdir(exist_ok=True)
    return path


def _get_insight_index_path() -> Path:
    return _get_insights_dir() / ".insight_index.json"

INSIGHT_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "in", "into", "is", "it", "its", "of", "on", "or", "that", "the", "their",
    "this", "to", "was", "were", "will", "with", "your", "you",
}

INSIGHT_TYPE_TO_DEPARTMENT = {
    "telemetry_finding": "telemetry",
    "strategy_insight": "strategy",
    "driver_analysis": "driver",
    "championship_outlook": "prediction",
    "race_prediction": "prediction",
    "technical_discovery": "news",
    "statistical_anomaly": "anomaly",
    "trend_analysis": "synthesis",
    "intelligence_report": "synthesis",
}


def _truncate_text(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]{2,}", (text or "").lower())
    return [token for token in tokens if token not in INSIGHT_STOPWORDS]


def _infer_department(insight_type: str, tags: list[str] | None = None) -> str:
    norm_type = _slug(insight_type)
    if norm_type in INSIGHT_TYPE_TO_DEPARTMENT:
        return INSIGHT_TYPE_TO_DEPARTMENT[norm_type]

    tag_tokens = {_slug(tag) for tag in (tags or [])}
    for tag in tag_tokens:
        if tag in {"telemetry", "strategy", "driver", "prediction", "news", "anomaly", "synthesis"}:
            return tag
    if "telemetry" in norm_type:
        return "telemetry"
    if "strategy" in norm_type:
        return "strategy"
    if "driver" in norm_type:
        return "driver"
    if "predict" in norm_type or "championship" in norm_type:
        return "prediction"
    if "technical" in norm_type or "news" in norm_type:
        return "news"
    if "anomaly" in norm_type or "statistical" in norm_type:
        return "anomaly"
    return "general"


def _short_summary(content: str, limit: int = 280) -> str:
    cleaned = _normalize_whitespace(content)
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    summary = parts[0]
    if len(parts) > 1 and len(summary) < max(80, limit // 2):
        summary = f"{summary} {parts[1]}"
    return _truncate_text(summary, limit)


def _extract_markdown_entries(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    sections = re.split(r"\n---\n", text)
    entries = []
    for section in sections:
        title_match = re.search(r"^##\s+(.+)$", section, flags=re.MULTILINE)
        type_match = re.search(r"\*\*Type:\*\*\s*(.+?)(?:\s*\||\s*$)", section, flags=re.MULTILINE)
        confidence_match = re.search(r"\*\*Confidence:\*\*\s*(.+?)(?:\s*\||\s*$)", section, flags=re.MULTILINE)
        time_match = re.search(r"\*\*(?:Time|Published):\*\*\s*(.+?)(?:\s*\||\s*$)", section, flags=re.MULTILINE)
        tags_match = re.search(r"^\*\*Tags:\*\*\s*(.*)$", section, flags=re.MULTILINE)
        if not title_match or not type_match:
            continue

        title = _normalize_whitespace(title_match.group(1))
        insight_type = _normalize_whitespace(type_match.group(1))
        confidence_raw = _normalize_whitespace(confidence_match.group(1) if confidence_match else "")
        timestamp = _normalize_whitespace(time_match.group(1) if time_match else "")
        tags = [tag.strip() for tag in (tags_match.group(1) if tags_match else "").split(",") if tag.strip()]

        last_meta_end = max(
            title_match.end(),
            type_match.end(),
            confidence_match.end() if confidence_match else 0,
            time_match.end() if time_match else 0,
            tags_match.end() if tags_match else 0,
        )
        body_start = section.find("\n\n", last_meta_end)
        content = section[body_start:].strip() if body_start != -1 else ""
        department = _infer_department(insight_type, tags)
        content = _normalize_whitespace(content)
        content_tokens = _tokenize(f"{title} {' '.join(tags)} {content}")

        entries.append({
            "id": f"{path.name}:{_slug(title)}",
            "title": title,
            "insight_type": insight_type,
            "department": department,
            "confidence": confidence_raw,
            "timestamp": timestamp,
            "date": path.name[:10],
            "file": str(path),
            "tags": tags,
            "summary": _short_summary(content),
            "content": content,
            "tokens": content_tokens,
        })
    return entries


def _insight_files() -> list[Path]:
    insights_dir = _get_insights_dir()
    return sorted(
        [path for path in insights_dir.glob("*.md") if not path.name.startswith(".")],
        reverse=True,
    )


def _load_index() -> dict:
    insight_index_path = _get_insight_index_path()
    if not insight_index_path.exists():
        return {"built_at": None, "entries": [], "files": {}}
    try:
        return json.loads(insight_index_path.read_text(encoding="utf-8"))
    except Exception:
        return {"built_at": None, "entries": [], "files": {}}


def _rebuild_index_if_needed(force: bool = False) -> dict:
    index = _load_index()
    files = _insight_files()
    current_state = {
        str(path): {"mtime": path.stat().st_mtime, "size": path.stat().st_size}
        for path in files
    }
    if not force and index.get("files") == current_state and index.get("entries") is not None:
        return index

    entries = []
    for path in files:
        entries.extend(_extract_markdown_entries(path))

    index = {
        "built_at": datetime.now().isoformat(),
        "files": current_state,
        "entries": entries,
    }
    _get_insight_index_path().write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


def _parse_date_filter(date_filter: str) -> tuple[Optional[datetime], Optional[datetime], Optional[str]]:
    now = datetime.now()
    if date_filter == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0), now, None
    if date_filter == "this_week":
        return now - timedelta(days=7), now, None
    if date_filter == "all":
        return None, None, None
    return None, None, date_filter


def _filter_entries(entries: list[dict], date_filter: str = "all", department: str = "", insight_type: str = "") -> list[dict]:
    start, end, exact_date = _parse_date_filter((date_filter or "all").strip())
    department = _slug(department)
    insight_type = _slug(insight_type)

    filtered = []
    for entry in entries:
        entry_date = entry.get("date", "")
        if exact_date and entry_date != exact_date:
            continue
        if start or end:
            try:
                entry_dt = datetime.strptime(entry_date, "%Y-%m-%d")
            except Exception:
                continue
            if start and entry_dt < start.replace(tzinfo=None):
                continue
            if end and entry_dt > end.replace(tzinfo=None):
                continue
        if department and _slug(entry.get("department", "")) != department:
            continue
        if insight_type and _slug(entry.get("insight_type", "")) != insight_type:
            continue
        filtered.append(entry)
    return filtered


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = left & right
    union = left | right
    return len(overlap) / max(1, len(union))


def _score_entry(query: str, entry: dict) -> float:
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        query_tokens = set(_tokenize(entry.get("title", "")))
    entry_tokens = set(entry.get("tokens", []))
    if not entry_tokens:
        entry_tokens = set(_tokenize(" ".join([
            entry.get("title", ""),
            entry.get("summary", ""),
            " ".join(entry.get("tags", [])),
        ])))

    title_tokens = set(_tokenize(entry.get("title", "")))
    summary_tokens = set(_tokenize(entry.get("summary", "")))
    title_overlap = _jaccard_similarity(query_tokens, title_tokens)
    body_overlap = _jaccard_similarity(query_tokens, entry_tokens)
    summary_overlap = _jaccard_similarity(query_tokens, summary_tokens)
    score = (0.45 * title_overlap) + (0.4 * body_overlap) + (0.15 * summary_overlap)
    return round(score, 4)


def _render_entry(entry: dict, include_content: bool = False) -> dict:
    rendered = {
        "title": entry.get("title", ""),
        "department": entry.get("department", ""),
        "insight_type": entry.get("insight_type", ""),
        "date": entry.get("date", ""),
        "confidence": entry.get("confidence", ""),
        "tags": entry.get("tags", []),
        "summary": entry.get("summary", ""),
        "file": entry.get("file", ""),
    }
    if include_content:
        rendered["content"] = _truncate_text(entry.get("content", ""), 420)
    return rendered


def _fit_json_budget(payload: dict, max_chars: int) -> str:
    max_chars = max(300, int(max_chars or 1800))
    working = json.loads(json.dumps(payload))

    def render() -> str:
        return json.dumps(working, indent=2)

    rendered = render()
    if len(rendered) <= max_chars:
        return rendered

    list_key = "matches" if "matches" in working else "insights" if "insights" in working else None
    if list_key:
        while len(working.get(list_key, [])) > 1 and len(render()) > max_chars:
            working[list_key] = working[list_key][:-1]

        for item in working.get(list_key, []):
            if "content" in item:
                item["content"] = _truncate_text(item["content"], 220)
            item["summary"] = _truncate_text(item.get("summary", ""), 160)

        rendered = render()
        if len(rendered) <= max_chars:
            return rendered

    if "novelty_hint" in working:
        working["novelty_hint"] = _truncate_text(working["novelty_hint"], 120)

    rendered = render()
    if len(rendered) <= max_chars:
        return rendered

    minimal = {
        key: value for key, value in working.items()
        if key not in {"matches", "insights"}
    }
    if list_key and working.get(list_key):
        minimal[list_key] = [
            {
                "title": working[list_key][0].get("title", ""),
                "date": working[list_key][0].get("date", ""),
                "summary": _truncate_text(working[list_key][0].get("summary", ""), 120),
                "similarity": working[list_key][0].get("similarity"),
                "file": working[list_key][0].get("file", ""),
            }
        ]
    return json.dumps(minimal, indent=2)


def _find_similar_insights(
    query: str,
    department: str = "",
    date_filter: str = "all",
    insight_type: str = "",
    max_results: int = 5,
) -> list[dict]:
    entries = _filter_entries(
        _rebuild_index_if_needed().get("entries", []),
        date_filter=date_filter,
        department=department,
        insight_type=insight_type,
    )
    scored = []
    for entry in entries:
        score = _score_entry(query, entry)
        if score <= 0:
            continue
        enriched = dict(entry)
        enriched["similarity"] = score
        scored.append(enriched)
    scored.sort(key=lambda item: (item["similarity"], item.get("date", "")), reverse=True)
    return scored[: max(1, min(max_results, 8))]


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

    cache_file = _get_news_cache_dir() / f"{_cache_key(query)}.json"
    
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
    cache_file = _get_news_cache_dir() / f"facts_{_cache_key(query)}.json"
    
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
        insights_dir = _get_insights_dir()
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H:%M:%S")
        normalized_type = insight_type.lower().replace(" ", "_")
        fname    = insights_dir / f"{date_str}_{normalized_type}.md"
        
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        department = _infer_department(insight_type, tag_list)
        similarity_query = f"{title}. {content}. {' '.join(tag_list)}"
        similar_before_publish = _find_similar_insights(
            similarity_query,
            department=department,
            insight_type=insight_type,
            date_filter="all",
            max_results=3,
        )
        
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

        _rebuild_index_if_needed(force=True)
        
        return json.dumps({
            "status":    "published",
            "file":      str(fname),
            "title":     title,
            "department": department,
            "similar_insights": [
                {
                    "title": item["title"],
                    "date": item["date"],
                    "similarity": item["similarity"],
                    "file": item["file"],
                }
                for item in similar_before_publish
                if item.get("title") != title
            ],
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 4: Read Previously Published Insights
# ══════════════════════════════════════════════════════════════════════════════
@tool("read_published_insights")
def read_published_insights(
    date_filter: str = "today",
    max_chars: int = 1800,
    department: str = "",
    insight_type: str = "",
) -> str:
    """
    Read previously published F1 research insights. Use this to avoid
    duplicating research and to build on prior findings.
    date_filter: 'today' | 'this_week' | 'all' | specific date 'YYYY-MM-DD'
    department: optional department scope, e.g. telemetry | strategy | prediction
    insight_type: optional exact insight type scope, e.g. telemetry_finding

    Returns compact summaries only. For semantic recall, prefer
    `retrieve_relevant_insights` with a focused query.
    """
    try:
        insights_dir = _get_insights_dir()
        if not insights_dir.exists():
            return json.dumps({"status": "no_insights", "message": "No insights published yet"})

        entries = _filter_entries(
            _rebuild_index_if_needed().get("entries", []),
            date_filter=date_filter,
            department=department,
            insight_type=insight_type,
        )
        if not entries:
            return json.dumps({"status": "empty", "message": "No insights found for filter"})

        rendered = [_render_entry(entry, include_content=False) for entry in entries[:8]]
        payload = {
            "filter": date_filter,
            "department": department or None,
            "insight_type": insight_type or None,
            "count": len(entries),
            "insights": rendered,
        }
        return _fit_json_budget(payload, max_chars)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool("retrieve_relevant_insights")
def retrieve_relevant_insights(
    query: str,
    department: str = "",
    date_filter: str = "all",
    max_results: int = 4,
    max_chars: int = 1800,
) -> str:
    """
    Semantic-ish local RAG over previously published insights.

    Use this before publishing a new finding or when you need department memory.
    Keep the query short and specific to the claim/topic you are investigating.

    Returns ranked compact snippets only, so large historical files do not get
    pushed directly into the agent context.
    """
    try:
        query = _normalize_whitespace(query)
        if not query:
            return json.dumps({"error": "query is required"})

        max_results = max(1, min(int(max_results), 6))
        matches = _find_similar_insights(
            query=query,
            department=department,
            date_filter=date_filter,
            max_results=max_results,
        )
        if not matches:
            return json.dumps({
                "query": query,
                "department": department or None,
                "matches": [],
                "novelty_hint": "No similar prior insight found in the selected memory scope.",
            })

        top_score = matches[0]["similarity"]
        novelty_hint = (
            "High overlap with prior findings. Only publish if you have materially new evidence, a narrower claim, or a changed confidence level."
            if top_score >= 0.32
            else "Only partial overlap with prior findings. You may have room for a genuinely new angle."
        )
        payload = {
            "query": query,
            "department": department or None,
            "date_filter": date_filter,
            "matches": [
                {
                    **_render_entry(match, include_content=True),
                    "similarity": match["similarity"],
                }
                for match in matches
            ],
            "novelty_hint": novelty_hint,
        }
        return _fit_json_budget(payload, max_chars)
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
    retrieve_relevant_insights,
    get_next_race_info,
]
