"""
F1 Research Program - Comprehensive Logging Infrastructure
Separate log files for: agent conversations, tool calls, LLM responses,
overall summaries, telemetry analysis, and insights published.
"""

import logging
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from functools import wraps
import traceback
import threading

# ── Thread-safe log directory setup ────────────────────────────────────────
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

SESSION_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
SESSION_DIR = LOGS_DIR / SESSION_ID
SESSION_DIR.mkdir(exist_ok=True)

_log_lock = threading.Lock()

# ── ANSI colors for terminal ────────────────────────────────────────────────
class Colors:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    ORANGE  = "\033[38;5;208m"
    GREY    = "\033[90m"

# ── Custom formatter for beautiful terminal output ──────────────────────────
class F1Formatter(logging.Formatter):
    LEVEL_COLORS = {
        "DEBUG":    Colors.GREY,
        "INFO":     Colors.CYAN,
        "WARNING":  Colors.YELLOW,
        "ERROR":    Colors.RED,
        "CRITICAL": Colors.RED + Colors.BOLD,
    }
    
    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelname, Colors.WHITE)
        ts    = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        name  = record.name.replace("f1_research.", "")[:20].ljust(20)
        msg   = super().format(record)
        return (
            f"{Colors.GREY}[{ts}]{Colors.RESET} "
            f"{color}{record.levelname:<8}{Colors.RESET} "
            f"{Colors.MAGENTA}{name}{Colors.RESET} │ {msg}"
        )

# ── File formatter (no colors) ──────────────────────────────────────────────
class FileFormatter(logging.Formatter):
    def format(self, record):
        ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        msg = super().format(record)
        return f"[{ts}] [{record.levelname:<8}] [{record.name}] {msg}"

# ── JSON formatter for structured logs ─────────────────────────────────────
class JSONFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.getMessage(),
            "session":   SESSION_ID,
        }
        if hasattr(record, "extra_data"):
            entry["data"] = record.extra_data
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)

# ── Logger factory ──────────────────────────────────────────────────────────
def _make_logger(name: str, filename: str, level=logging.DEBUG, json_mode=False) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    
    # File handler
    fh = logging.FileHandler(SESSION_DIR / filename, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(JSONFormatter() if json_mode else FileFormatter())
    logger.addHandler(fh)
    
    return logger

def _make_console_logger(name: str, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(f"console.{name}")
    logger.setLevel(level)
    logger.propagate = False
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(F1Formatter())
    logger.addHandler(ch)
    return logger

# ── Dedicated loggers ───────────────────────────────────────────────────────
agent_logger       = _make_logger("f1_research.agents",       "agent_conversations.log")
tool_logger        = _make_logger("f1_research.tools",        "tool_calls.log", json_mode=True)
llm_logger         = _make_logger("f1_research.llm",          "llm_responses.log")
summary_logger     = _make_logger("f1_research.summary",      "research_summary.log")
telemetry_logger   = _make_logger("f1_research.telemetry",    "telemetry_analysis.log")
insight_logger     = _make_logger("f1_research.insights",     "published_insights.log")
news_logger        = _make_logger("f1_research.news",         "news_feed.log")
prediction_logger  = _make_logger("f1_research.predictions",  "race_predictions.log")
debate_logger      = _make_logger("f1_research.debate",       "agent_debates.log")
error_logger       = _make_logger("f1_research.errors",       "errors.log", json_mode=True)
perf_logger        = _make_logger("f1_research.performance",  "performance.log")
task_logger        = _make_logger("f1_research.tasks",        "task_events.log", json_mode=True)

# Console logger (shown in terminal)
console = _make_console_logger("main")
console.addHandler(logging.StreamHandler(sys.stdout))
console.handlers[0].setFormatter(F1Formatter())

# Also add file handler to console log
_console_fh = logging.FileHandler(SESSION_DIR / "console_output.log", encoding="utf-8")
_console_fh.setFormatter(FileFormatter())
console.addHandler(_console_fh)

_task_context = threading.local()


def set_task_context(context: dict | None) -> None:
    payload = dict(context or {})
    payload.setdefault("tools_used", [])
    _task_context.value = payload


def get_task_context() -> dict:
    return dict(getattr(_task_context, "value", {}) or {})


def clear_task_context() -> None:
    _task_context.value = {}

# ── Convenience logging functions ───────────────────────────────────────────

def log_agent_message(agent_name: str, message_type: str, content: str, 
                       to_agent: Optional[str] = None):
    """Log inter-agent messages and conversations."""
    sep = "─" * 60
    header = f"\n{sep}\n🤖 AGENT: {agent_name}"
    if to_agent:
        header += f" → {to_agent}"
    header += f" | TYPE: {message_type}\n{sep}"
    agent_logger.info(f"{header}\n{content}\n")
    console.info(f"💬 {Colors.GREEN}{agent_name}{Colors.RESET} [{message_type}]")

def log_debate_round(round_num: int, agent_name: str, position: str, argument: str):
    """Log agent debate/discussion rounds."""
    sep = "═" * 70
    debate_logger.info(
        f"\n{sep}\n🥊 DEBATE ROUND {round_num} | {agent_name}\n"
        f"POSITION: {position}\n{sep}\n{argument}\n"
    )
    console.info(f"🥊 Debate R{round_num}: {Colors.CYAN}{agent_name}{Colors.RESET} - {position[:80]}...")

def log_tool_call(agent_name: str, tool_name: str, inputs: dict, output: Any, 
                   duration_ms: float = 0):
    """Log tool calls with inputs/outputs."""
    record = logging.LogRecord(
        name="f1_research.tools", level=logging.INFO,
        pathname="", lineno=0, msg="",
        args=(), exc_info=None
    )
    live_context = getattr(_task_context, "value", {}) or {}
    if isinstance(live_context, dict):
        tools_used = live_context.setdefault("tools_used", [])
        if tool_name not in tools_used:
            tools_used.append(tool_name)
    task_context = get_task_context()
    record.extra_data = {
        "agent":       agent_name,
        "tool":        tool_name,
        "inputs":      inputs,
        "output_preview": str(output)[:500] if output else None,
        "duration_ms": round(duration_ms, 2),
        "task":        task_context or None,
    }
    tool_logger.handle(record)
    console.debug(f"🔧 Tool: {Colors.ORANGE}{tool_name}{Colors.RESET} by {agent_name} ({duration_ms:.0f}ms)")

def log_llm_request(agent_name: str, model: str, prompt_tokens: int, 
                     system_prompt: str, user_message: str):
    """Log LLM requests."""
    llm_logger.debug(
        f"\n{'─'*60}\n📤 LLM REQUEST | Agent: {agent_name} | Model: {model}\n"
        f"Tokens(est): {prompt_tokens}\n"
        f"SYSTEM:\n{system_prompt[:300]}...\n"
        f"USER:\n{user_message[:500]}...\n"
    )

def log_llm_response(agent_name: str, model: str, response: str, 
                      completion_tokens: int = 0, duration_ms: float = 0):
    """Log LLM responses."""
    llm_logger.info(
        f"\n{'─'*60}\n📥 LLM RESPONSE | Agent: {agent_name} | Model: {model}\n"
        f"Duration: {duration_ms:.0f}ms | Tokens: {completion_tokens}\n"
        f"{'─'*40}\n{response}\n"
    )

def log_telemetry_analysis(analysis_type: str, session_info: str, 
                            findings: str, metrics: dict):
    """Log telemetry analysis results."""
    sep = "━" * 70
    telemetry_logger.info(
        f"\n{sep}\n📊 TELEMETRY ANALYSIS | {analysis_type}\n"
        f"Session: {session_info}\n{sep}\n"
        f"FINDINGS:\n{findings}\n\n"
        f"KEY METRICS:\n{json.dumps(metrics, indent=2)}\n"
    )
    console.info(f"📊 Telemetry: {Colors.BLUE}{analysis_type}{Colors.RESET}")

def log_insight(insight_type: str, title: str, content: str, 
                confidence: float = 0.0, tags: list = None):
    """Log a published insight."""
    ts   = datetime.now().isoformat()
    tags = tags or []
    insight_logger.info(
        f"\n{'★'*70}\n💡 INSIGHT PUBLISHED | {ts}\n"
        f"Type: {insight_type} | Confidence: {confidence:.0%}\n"
        f"Title: {title}\nTags: {', '.join(tags)}\n"
        f"{'─'*70}\n{content}\n{'★'*70}\n"
    )
    # Also write to insights directory as markdown
    _write_insight_file(insight_type, title, content, confidence, tags, ts)
    console.info(f"💡 {Colors.YELLOW}INSIGHT:{Colors.RESET} {title}")

def _write_insight_file(insight_type, title, content, confidence, tags, ts):
    """Write insight to dated markdown file."""
    insights_dir = Path("insights")
    insights_dir.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    fname    = insights_dir / f"{date_str}_{insight_type.lower().replace(' ','_')}.md"
    
    entry = (
        f"\n---\n"
        f"## {title}\n"
        f"**Type:** {insight_type} | **Confidence:** {confidence:.0%} | **Time:** {ts}\n"
        f"**Tags:** {', '.join(tags)}\n\n"
        f"{content}\n"
    )
    with _log_lock:
        with open(fname, "a", encoding="utf-8") as f:
            if fname.stat().st_size == 0 if fname.exists() else False:
                f.write(f"# F1 Research Insights - {date_str}\n")
            f.write(entry)

def log_prediction(race_name: str, prediction_type: str, 
                   prediction: str, reasoning: str, confidence: float):
    """Log race predictions."""
    sep = "🏁" * 35
    prediction_logger.info(
        f"\n{sep}\n🏁 PREDICTION | {race_name} | {prediction_type}\n"
        f"Confidence: {confidence:.0%}\n{sep}\n"
        f"PREDICTION:\n{prediction}\n\n"
        f"REASONING:\n{reasoning}\n"
    )
    console.info(f"🏁 Prediction [{prediction_type}]: {Colors.GREEN}{race_name}{Colors.RESET} ({confidence:.0%})")

def log_news_item(source: str, title: str, summary: str, relevance: float):
    """Log F1 news items."""
    news_logger.info(
        f"\n📰 NEWS | Source: {source} | Relevance: {relevance:.0%}\n"
        f"Title: {title}\nSummary: {summary[:300]}\n"
    )

def log_error(component: str, error: Exception, context: str = ""):
    """Log errors with full traceback."""
    record = logging.LogRecord(
        name="f1_research.errors", level=logging.ERROR,
        pathname="", lineno=0, msg="",
        args=(), exc_info=sys.exc_info()
    )
    record.extra_data = {
        "component": component,
        "context":   context,
        "error":     str(error),
        "traceback": traceback.format_exc(),
    }
    error_logger.handle(record)
    console.error(f"❌ Error in {component}: {str(error)[:100]}")

def log_research_summary(session_summary: dict):
    """Log overall research session summary."""
    summary_logger.info(
        f"\n{'═'*70}\n📋 RESEARCH SESSION SUMMARY\n{'═'*70}\n"
        f"{json.dumps(session_summary, indent=2)}\n"
    )


def log_task_event(event_type: str, payload: dict):
    """Write a structured per-task event for later inspection."""
    record = logging.LogRecord(
        name="f1_research.tasks", level=logging.INFO,
        pathname="", lineno=0, msg=event_type,
        args=(), exc_info=None
    )
    record.extra_data = payload
    task_logger.handle(record)


def log_task_summary(crew_name: str, task_index: int, agent_role: str, summary: dict):
    """Append a readable task summary into research_summary.log."""
    summary_logger.info(
        f"\n{'─'*70}\n"
        f"TASK SUMMARY | Crew: {crew_name} | Task: {task_index + 1} | Agent: {agent_role}\n"
        f"{json.dumps(summary, indent=2)}\n"
    )

def log_performance(component: str, operation: str, duration_ms: float, metadata: dict = None):
    """Log performance metrics."""
    perf_logger.debug(
        f"⚡ PERF | {component} | {operation} | {duration_ms:.2f}ms | "
        f"{json.dumps(metadata or {})}"
    )

# ── Decorator for timing + logging functions ────────────────────────────────
def timed_log(component: str, operation: str):
    """Decorator: auto-times and logs performance of a function."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            start = datetime.now()
            try:
                result = fn(*args, **kwargs)
                duration = (datetime.now() - start).total_seconds() * 1000
                log_performance(component, operation, duration)
                return result
            except Exception as e:
                duration = (datetime.now() - start).total_seconds() * 1000
                log_error(component, e, f"In {operation} after {duration:.0f}ms")
                raise
        return wrapper
    return decorator

# ── Print session banner ────────────────────────────────────────────────────
def print_banner():
    banner = f"""
{Colors.RED}{'█'*70}{Colors.RESET}
{Colors.RED}█{Colors.RESET}{Colors.WHITE}{'F1 AUTONOMOUS RESEARCH PROGRAM':^68}{Colors.RESET}{Colors.RED}█{Colors.RESET}
{Colors.RED}█{Colors.RESET}{Colors.GREY}{'Powered by CrewAI | FastF1 | Multi-LLM Backend':^68}{Colors.RESET}{Colors.RED}█{Colors.RESET}
{Colors.RED}{'█'*70}{Colors.RESET}
{Colors.GREY}Session ID : {Colors.CYAN}{SESSION_ID}{Colors.RESET}
{Colors.GREY}Log Dir    : {Colors.CYAN}{SESSION_DIR}{Colors.RESET}
{Colors.GREY}Started    : {Colors.CYAN}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.RESET}
{'─'*70}
"""
    print(banner)

if __name__ == "__main__":
    print_banner()
    log_agent_message("TestAgent", "INFO", "Logger initialized successfully!")
    log_tool_call("TestAgent", "test_tool", {"input": "hello"}, "output", 42.5)
    log_insight("TEST", "Logger works!", "All log files are being written.", 0.99, ["test"])
    print(f"\n✅ Log files written to: {SESSION_DIR}")
