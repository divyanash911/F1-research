from __future__ import annotations

import json
from typing import Any

import httpx
try:
    # duckduckgo-search >= 8
    from duckduckgo_search import DDGS  # type: ignore
except Exception:  # pragma: no cover
    # older versions
    from duckduckgo_search.duckduckgo_search import DDGS  # type: ignore
from langchain_core.tools import tool
from langchain_experimental.tools import PythonREPLTool
import bs4

from .kb import JsonlKnowledgeBase

OPENF1_BASE = "https://api.openf1.org/v1"


def _openf1_get(endpoint: str, params: dict[str, Any] | None = None, timeout_s: float = 20.0) -> list[dict[str, Any]]:
    url = f"{OPENF1_BASE}/{endpoint}"
    # OpenF1 is public and can rate limit (429). Add a small retry w/ backoff to keep agents stable.
    with httpx.Client(timeout=timeout_s) as client:
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                r = client.get(url, params=params or {}, headers={"Accept": "application/json"})
                if r.status_code == 429:
                    # If provided, respect Retry-After; otherwise do exponential backoff.
                    import time

                    retry_after = r.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        time.sleep(float(retry_after))
                    else:
                        time.sleep(0.5 * (2**attempt))
                    continue

                if r.status_code == 404:
                    try:
                        data = r.json()
                        if data.get("detail") == "No results found.":
                            return []
                    except Exception:
                        pass

                r.raise_for_status()
                data = r.json()
                if isinstance(data, list):
                    return data
                return [data]
            except Exception as e:
                last_exc = e
                # brief backoff then retry
                import time

                time.sleep(0.25 * (2**attempt))

        if last_exc:
            raise last_exc
        raise RuntimeError("OpenF1 request failed")


@tool
def openf1_sessions(year: int = 2026, session_type: str | None = None) -> str:
    """Fetch OpenF1 sessions. Optionally filter by session_type (e.g. 'Race', 'Qualifying'). Returns JSON string."""
    params: dict[str, Any] = {"year": year}
    if session_type:
        params["session_type"] = session_type
    data = _openf1_get("sessions", params=params)
    return json.dumps(data[:200], ensure_ascii=False)


@tool
def openf1_meetings(year: int = 2026, country_name: str | None = None) -> str:
    """Fetch OpenF1 meetings (calendar). Optionally filter by country_name. Returns JSON string."""
    params: dict[str, Any] = {"year": year}
    if country_name:
        params["country_name"] = country_name
    data = _openf1_get("meetings", params=params)
    return json.dumps(data[:200], ensure_ascii=False)


@tool
def openf1_session_result(session_key: int, position_lte: int | None = 10) -> str:
    """Fetch session results for a session_key. Use position_lte to limit (default top 10). Returns JSON string."""
    params: dict[str, Any] = {"session_key": session_key}
    if position_lte is not None:
        params["position<="] = position_lte
    data = _openf1_get("session_result", params=params)
    return json.dumps(data, ensure_ascii=False)


@tool
def openf1_drivers(session_key: int | None = None, meeting_key: int | None = None) -> str:
    """Fetch drivers for a session_key or meeting_key. Returns JSON string."""
    params: dict[str, Any] = {}
    if session_key is not None:
        params["session_key"] = session_key
    if meeting_key is not None:
        params["meeting_key"] = meeting_key
    data = _openf1_get("drivers", params=params)
    return json.dumps(data[:200], ensure_ascii=False)


@tool
def openf1_positions(session_key: int, driver_number: int | None = None) -> str:
    """Fetch position timeline for a session. Returns JSON string."""
    params: dict[str, Any] = {"session_key": session_key}
    if driver_number is not None:
        params["driver_number"] = driver_number
    data = _openf1_get("position", params=params)
    return json.dumps(data[:5000], ensure_ascii=False)


@tool
def openf1_laps(session_key: int, driver_number: int | None = None) -> str:
    """Fetch laps for a session (optionally a single driver). Returns JSON string."""
    params: dict[str, Any] = {"session_key": session_key}
    if driver_number is not None:
        params["driver_number"] = driver_number
    data = _openf1_get("laps", params=params)
    return json.dumps(data[:5000], ensure_ascii=False)


@tool
def openf1_stints(session_key: int, driver_number: int | None = None) -> str:
    """Fetch stints for a session (optionally a single driver). Returns JSON string."""
    params: dict[str, Any] = {"session_key": session_key}
    if driver_number is not None:
        params["driver_number"] = driver_number
    data = _openf1_get("stints", params=params)
    return json.dumps(data[:1000], ensure_ascii=False)


@tool
def openf1_weather(session_key: int | None = None, meeting_key: int | None = None) -> str:
    """Fetch weather for a session or meeting. Returns JSON string."""
    params: dict[str, Any] = {}
    if session_key is not None:
        params["session_key"] = session_key
    if meeting_key is not None:
        params["meeting_key"] = meeting_key
    data = _openf1_get("weather", params=params)
    return json.dumps(data[:2000], ensure_ascii=False)


@tool
def openf1_intervals(session_key: int, driver_number: int | None = None) -> str:
    """Fetch interval/gap data for a session. Returns JSON string."""
    params: dict[str, Any] = {"session_key": session_key}
    if driver_number is not None:
        params["driver_number"] = driver_number
    data = _openf1_get("intervals", params=params)
    return json.dumps(data[:5000], ensure_ascii=False)


@tool
def openf1_race_control(session_key: int, flag: str | None = None, driver_number: int | None = None) -> str:
    """Fetch race control messages for a session. Returns JSON string."""
    params: dict[str, Any] = {"session_key": session_key}
    if flag:
        params["flag"] = flag
    if driver_number is not None:
        params["driver_number"] = driver_number
    data = _openf1_get("race_control", params=params)
    return json.dumps(data[:2000], ensure_ascii=False)


@tool
def openf1_team_radio(session_key: int, driver_number: int | None = None) -> str:
    """Fetch team radio records for a session. Returns JSON string."""
    params: dict[str, Any] = {"session_key": session_key}
    if driver_number is not None:
        params["driver_number"] = driver_number
    data = _openf1_get("team_radio", params=params)
    return json.dumps(data[:2000], ensure_ascii=False)


@tool
def openf1_pit(session_key: int, driver_number: int | None = None) -> str:
    """Fetch pit stop data for a session. Returns JSON string."""
    params: dict[str, Any] = {"session_key": session_key}
    if driver_number is not None:
        params["driver_number"] = driver_number
    data = _openf1_get("pit", params=params)
    return json.dumps(data[:2000], ensure_ascii=False)


@tool
def openf1_overtakes(session_key: int, overtaking_driver_number: int | None = None) -> str:
    """Fetch overtakes for a session. Returns JSON string."""
    params: dict[str, Any] = {"session_key": session_key}
    if overtaking_driver_number is not None:
        params["overtaking_driver_number"] = overtaking_driver_number
    data = _openf1_get("overtakes", params=params)
    return json.dumps(data[:2000], ensure_ascii=False)


@tool
def openf1_race_control(session_key: int, flag: str | None = None, driver_number: int | None = None) -> str:
    """Fetch race control messages for a session. Returns JSON string."""
    params: dict[str, Any] = {"session_key": session_key}
    if flag:
        params["flag"] = flag
    if driver_number is not None:
        params["driver_number"] = driver_number
    data = _openf1_get("race_control", params=params)
    return json.dumps(data[:2000], ensure_ascii=False)


# -----------------------------
# Higher-level research helpers
# -----------------------------


@tool
def openf1_meetings_for_year(year: int = 2026) -> str:
    """Convenience wrapper around meetings(year=...). Returns JSON string."""
    data = _openf1_get("meetings", params={"year": year})
    return json.dumps(data[:200], ensure_ascii=False)


@tool
def openf1_races_for_year(year: int = 2026) -> str:
    """Fetch Race sessions for a year (calendar of races). Returns JSON string."""
    data = _openf1_get("sessions", params={"year": year, "session_type": "Race"})
    return json.dumps(data[:60], ensure_ascii=False)


@tool
def openf1_driver_race_results(year: int = 2026, driver_number: int | None = None, limit: int = 50) -> str:
    """Fetch race results across a season, optionally for one driver. Returns JSON string."""
    races = _openf1_get("sessions", params={"year": year, "session_type": "Race"})
    session_keys = [r.get("session_key") for r in races if r.get("session_key") is not None]

    all_rows: list[dict[str, Any]] = []
    for sk in session_keys:
        params: dict[str, Any] = {"session_key": sk}
        if driver_number is not None:
            params["driver_number"] = driver_number
        rows = _openf1_get("session_result", params=params)
        all_rows.extend(rows)
        if len(all_rows) >= limit:
            break

    return json.dumps(all_rows[:limit], ensure_ascii=False)


@tool
def openf1_driver_stints_across_races(driver_number: int, year: int = 2026, limit: int = 200) -> str:
    """Fetch tyre stints for a driver across race sessions in a year (for compound usage). Returns JSON string."""
    races = _openf1_get("sessions", params={"year": year, "session_type": "Race"})
    session_keys = [r.get("session_key") for r in races if r.get("session_key") is not None]
    all_rows: list[dict[str, Any]] = []
    for sk in session_keys:
        rows = _openf1_get("stints", params={"session_key": sk, "driver_number": driver_number})
        all_rows.extend(rows)
        if len(all_rows) >= limit:
            break
    return json.dumps(all_rows[:limit], ensure_ascii=False)


@tool
def openf1_weather_for_race_sessions(year: int = 2026, limit: int = 2000) -> str:
    """Fetch weather samples for all race sessions in a season. Returns JSON string."""
    races = _openf1_get("sessions", params={"year": year, "session_type": "Race"})
    session_keys = [r.get("session_key") for r in races if r.get("session_key") is not None]
    all_rows: list[dict[str, Any]] = []
    for sk in session_keys:
        rows = _openf1_get("weather", params={"session_key": sk})
        all_rows.extend(rows)
        if len(all_rows) >= limit:
            break
    return json.dumps(all_rows[:limit], ensure_ascii=False)


@tool
def web_search(query: str, max_results: int = 5, require_f1: bool = True) -> str:
    """Web search via DuckDuckGo.

    Tips:
    - Use specific queries (team/driver + date range + "2026" + "FIA"/"upgrade"/"statement").
    - When require_f1=True (default), the query is automatically biased toward Formula 1 sources.

    Returns JSON string with title, href, snippet.
    """
    results: list[dict[str, Any]] = []
    q = query
    if require_f1:
        q = f"Formula 1 2026 {query}"
    with DDGS() as ddgs:
        for r in ddgs.text(q, max_results=max_results):
            results.append(
                {
                    "title": r.get("title"),
                    "href": r.get("href"),
                    "snippet": r.get("body"),
                }
            )
    return json.dumps(results, ensure_ascii=False)


def make_kb_tools(kb: JsonlKnowledgeBase):
    @tool
    def kb_search(query: str, namespace: str = "default", limit: int = 8) -> str:
        """Search the long-term knowledge base for a query within a namespace. Returns JSON string."""
        hits = kb.search(query=query, namespace=namespace, limit=limit)
        return json.dumps([h.__dict__ for h in hits], ensure_ascii=False)

    @tool
    def kb_add(text: str, namespace: str = "default", metadata_json: str | None = None) -> str:
        """Add a memory record to the long-term knowledge base. metadata_json must be a JSON object string."""
        metadata: dict[str, Any] = {}
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
                if not isinstance(metadata, dict):
                    metadata = {"value": metadata}
            except json.JSONDecodeError:
                metadata = {"raw": metadata_json}
        rec = kb.add(namespace=namespace, text=text, metadata=metadata)
        return json.dumps(rec.__dict__, ensure_ascii=False)

    return [kb_search, kb_add]

@tool
def scrape_webpage(url: str) -> str:
    """Scrape and extract the main text content of a webpage. Useful for reading full articles.
    
    Returns the text content of the page, up to 15000 characters.
    """
    try:
        r = httpx.get(url, timeout=15.0)
        r.raise_for_status()
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
            
        text = soup.get_text(separator="\n")
        
        # Breakdown into lines and remove leading and trailing space on each
        lines = (line.strip() for line in text.splitlines())
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Drop blank lines
        text = "\n".join(chunk for chunk in chunks if chunk)
        
        return text[:15000]
    except Exception as e:
        return f"Failed to scrape webpage: {e}"

python_repl = PythonREPLTool()

