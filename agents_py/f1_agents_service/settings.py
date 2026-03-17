from __future__ import annotations

from pydantic import BaseModel


class Settings(BaseModel):
    """Runtime settings via environment variables."""

    # LLM provider (OpenAI-compatible)
    llm_provider: str = "groq"  # groq | openrouter | ollama
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"

    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # OpenRouter-required headers (recommended)
    openrouter_http_referer: str = "http://localhost:3000"
    openrouter_x_title: str = "F1 Intelligence Platform"

    # Ollama
    # Modes:
    # - openai: uses Ollama's OpenAI-compatible API (chat/completions) at base URL ending with /v1
    # - native: uses Ollama's native endpoint POST /api/generate (prompt-based)
    ollama_mode: str = "openai"  # openai | native
    # In openai mode, set to e.g. http://localhost:11434/v1
    # In native mode, set to e.g. http://localhost:11434 (if /v1 is included, it'll be stripped)
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_api_key: str = "ollama"  # not required by Ollama, but tolerated by OpenAI clients

    default_model: str = "llama-3.3-70b-versatile"

    # Knowledge base
    kb_path: str = "./data/kb.jsonl"


def get_settings() -> Settings:
    import os

    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", os.getenv("AGENTS_LLM_PROVIDER", "openrouter")),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        groq_base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        openrouter_http_referer=os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost:3000"),
        openrouter_x_title=os.getenv("OPENROUTER_X_TITLE", "F1 Intelligence Platform"),
        ollama_mode=os.getenv("OLLAMA_MODE", "openai"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        ollama_api_key=os.getenv("OLLAMA_API_KEY", "ollama"),
        default_model=os.getenv("LLM_MODEL", os.getenv("AGENTS_MODEL", "llama-3.3-70b-versatile")),
        kb_path=os.getenv("AGENTS_KB_PATH", "./data/kb.jsonl"),
    )
