"""
F1 Research Program - Multi-Backend LLM Configuration
Supports: Ollama (local) | OpenRouter (cloud, many models) | Groq (fast inference)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

# ── Backend selector ────────────────────────────────────────────────────────
# NOTE: this is the default backend. The orchestrator can override at runtime
# via `set_backend()`.
BACKEND = os.getenv("LLM_BACKEND", "groq").lower()

# Optional ordered list of providers to try when the current provider fails.
# Example: LLM_BACKEND_ORDER=groq,openrouter,ollama
BACKEND_ORDER = [
    b.strip().lower()
    for b in os.getenv("LLM_BACKEND_ORDER", "groq,openrouter,ollama").split(",")
    if b.strip()
]


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _infer_small_model(model_name: str) -> bool:
    name = (model_name or "").lower()
    hints = ("8b", "7b", "mini", "small", "instant", "1b", "3b")
    return any(hint in name for hint in hints)


def is_small_model_mode(backend: str | None = None, fast: bool = False) -> bool:
    """Return whether we should optimize prompts/agents for a fragile small model."""
    backend = (backend or BACKEND).upper()
    env_name = f"{backend}_{'FAST_' if fast else ''}MODEL"
    model_name = os.getenv(env_name, "")
    if _env_flag("SMALL_MODEL_MODE", default=False):
        return True
    return _infer_small_model(model_name)


def get_runtime_llm_settings(backend: str | None = None, fast: bool = False, conservative: bool = False) -> dict:
    """Centralize runtime knobs so retries can rebuild with stricter settings."""
    small_model = is_small_model_mode(backend=backend, fast=fast)
    temperature = 0.7
    timeout = 90
    max_tokens = 1000

    if small_model:
        temperature = 0.8
        timeout = 120
        max_tokens = 1600 if fast else 2200

    if conservative:
        temperature = min(temperature, 0.2)
        timeout = max(timeout, 150)
        max_tokens = min(max_tokens, 1200 if fast else 1600)

    return {
        "temperature": temperature,
        "timeout": timeout,
        "max_tokens": max_tokens,
        "small_model": small_model,
        "conservative": conservative,
    }


def set_backend(backend: str) -> None:
    """Set the current backend for *this process*.

    This lets the orchestrator rotate providers on transient LLM failures.
    """
    global BACKEND
    BACKEND = (backend or "").lower().strip()


def get_llm(fast: bool = False, conservative: bool = False):
    """
    Returns a CrewAI-compatible LLM object for the configured backend.

    Args:
        fast: If True, returns the faster/cheaper model for tool-heavy agents.
              If False, returns the main capable model for reasoning agents.
    """
    from crewai import LLM

    return get_llm_for_backend(BACKEND, fast=fast, conservative=conservative)


def get_llm_for_backend(backend: str, fast: bool = False, conservative: bool = False):
    """Return an LLM for a specific backend (does not mutate global BACKEND)."""
    backend = (backend or "").lower().strip()
    if backend == "ollama":
        return _ollama_llm(fast, conservative=conservative)
    if backend == "openrouter":
        return _openrouter_llm(fast, conservative=conservative)
    if backend == "groq":
        return _groq_llm(fast, conservative=conservative)
    raise ValueError(f"Unknown LLM backend: {backend}. Use ollama | openrouter | groq")


# ── Ollama (local) ──────────────────────────────────────────────────────────
def _ollama_llm(fast: bool, conservative: bool = False):
    from crewai import LLM

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    if fast:
        model = os.getenv("OLLAMA_FAST_MODEL", "llama3.1:8b")
    else:
        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

    settings = get_runtime_llm_settings("ollama", fast=fast, conservative=conservative)

    # LiteLLM's native Ollama chat provider uses /api/chat and supports tool calling.
    litellm_model = f"ollama_chat/{model}"
    normalized_base_url = base_url.rstrip("/")

    print(f"🦙 Ollama | model: {model} | endpoint: /api/chat | url: {normalized_base_url}")
    return LLM(
        model=litellm_model,
        base_url=normalized_base_url,
        api_base=normalized_base_url,
        api_key="ollama",
        temperature=settings["temperature"], 
        timeout=max(500, settings["timeout"]),
        max_tokens=min(1000 * 2, settings["max_tokens"]),
    )


# ── OpenRouter ──────────────────────────────────────────────────────────────
def _openrouter_llm(fast: bool, conservative: bool = False):
    from crewai import LLM

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key or api_key == "your_openrouter_api_key_here":
        raise ValueError("OPENROUTER_API_KEY not set in .env")

    if fast:
        model = os.getenv("OPENROUTER_FAST_MODEL", "meta-llama/llama-3.1-8b-instruct")
    else:
        model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")

    settings = get_runtime_llm_settings("openrouter", fast=fast, conservative=conservative)

    print(f"🌐 OpenRouter | model: {model}")
    return LLM(
        model=f"openrouter/{model}",
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=settings["temperature"],
        timeout=settings["timeout"],
        max_tokens=min(settings["max_tokens"], 1400),
    )


# ── Groq ─────────────────────────────────────────────────────────────────────
def _groq_llm(fast: bool, conservative: bool = False):
    from crewai import LLM

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key == "your_groq_api_key_here":
        raise ValueError("GROQ_API_KEY not set in .env")

    if fast:
        model = os.getenv("GROQ_FAST_MODEL", "llama-3.1-8b-instant")
    else:
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    settings = get_runtime_llm_settings("groq", fast=fast, conservative=conservative)

    print(f"⚡ Groq | model: {model}")
    return LLM(
        model=f"groq/{model}",
        api_key=api_key,
        temperature=settings["temperature"],
        timeout=settings["timeout"],
        max_tokens=settings["max_tokens"],
    )


# ── Backend info ──────────────────────────────────────────────────────────────
def get_backend_info() -> dict:
    return {
        "backend":        BACKEND,
        "main_model":     os.getenv(f"{BACKEND.upper()}_MODEL", "unknown"),
        "fast_model":     os.getenv(f"{BACKEND.upper()}_FAST_MODEL", "unknown"),
        "f1_season":      os.getenv("F1_SEASON", "2026"),
        "research_depth": os.getenv("RESEARCH_DEPTH", "deep"),
    }


def get_backend_order() -> list[str]:
    """Ordered backends to try for fallback."""
    # Ensure current BACKEND is included (front) even if env order omitted it.
    order = [BACKEND] + [b for b in BACKEND_ORDER if b != BACKEND]
    # Deduplicate, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for b in order:
        if b and b not in seen:
            seen.add(b)
            out.append(b)
    return out
