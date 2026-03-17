from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

import logging
import os
import time

from .agent_graph import build_agent, run_agent
from .kb import JsonlKnowledgeBase
from .settings import get_settings
from .autonomous.store import InsightStore
from .autonomous.scheduler import JobScheduler
from .autonomous.corporation import F1ResearchCorporation
from fastapi import HTTPException


class AgentRunRequest(BaseModel):
    message: str = Field(..., description="User question / task")
    agent_type: str = Field(
        default="general",
        description=(
            "Which specialized agent to run: general | news | season_form | telemetry | "
            "tyre_weather | predict_pipeline"
        ),
    )
    namespace: str = Field(default="default", description="KB namespace")
    extra_system: str | None = Field(default=None, description="Extra system instructions")


class AgentRunResponse(BaseModel):
    answer: str
    tool_calls: list[dict]
    trace: dict | None = None


def create_app() -> FastAPI:
    # Load env vars from the repo root `.env.local` (Next.js convention) if present.
    # This avoids needing to `export GROQ_API_KEY=...` before running uvicorn.
    # Never print secret values; we only log presence/absence.
    from pathlib import Path

    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    env_candidates = [
        repo_root / ".env.local",
        repo_root / ".env",
        repo_root / "agents_py" / ".env",
    ]
    try:
        from dotenv import load_dotenv

        loaded_any = False
        for p in env_candidates:
            if p.exists():
                load_dotenv(p, override=False)
                loaded_any = True
        if not loaded_any:
            logging.getLogger("f1_agents.env").warning(
                "No dotenv files found (looked for %s)",
                ", ".join(str(p) for p in env_candidates),
            )
    except Exception as e:
        logging.getLogger("f1_agents.env").warning(
            "python-dotenv not available or failed to load .env files (%s). "
            "Environment variables must be provided externally.",
            e,
        )

    settings = get_settings()

    # Log only existence of key (never the value) so misconfig is obvious.
    logging.getLogger("f1_agents.env").info(
        "LLM_PROVIDER=%s OPENROUTER_API_KEY_set=%s GROQ_API_KEY_set=%s OLLAMA_BASE_URL=%s",
        os.getenv("LLM_PROVIDER", ""),
        bool(os.getenv("OPENROUTER_API_KEY")),
        bool(os.getenv("GROQ_API_KEY")),
        os.getenv("OLLAMA_BASE_URL", ""),
    )

    # Basic logging config (override with AGENTS_LOG_LEVEL / AGENTS_DEBUG).
    level = os.getenv("AGENTS_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    if os.getenv("AGENTS_DEBUG", "0") == "1":
        logging.getLogger("f1_agents").setLevel(logging.DEBUG)
        logging.getLogger("f1_agents.agent").setLevel(logging.DEBUG)

    kb = JsonlKnowledgeBase(settings.kb_path)
    # Lazy-build specialized agents on demand.
    agents_cache: dict[str, object] = {}

    # Autonomous corporation (scheduler + publisher)
    store_path = os.getenv("AUTONOMOUS_STORE_PATH", "./data/insights.jsonl")
    insight_store = InsightStore(store_path)
    sched_path = os.getenv("AUTONOMOUS_SCHEDULER_DB", "./data/autonomous_jobs.sqlite")
    scheduler = JobScheduler(sched_path)
    corporation = F1ResearchCorporation(settings=settings, kb=kb, scheduler=scheduler, store=insight_store)

    app = FastAPI(title="F1 Agents Service", version="0.1.0")

    @app.on_event("startup")
    async def _startup():
        # Start the background workers if enabled.
        corporation.start()

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/debug/llm")
    async def debug_llm():
        """Minimal LLM smoke test.

        Returns a short completion for a trivial prompt. Useful for diagnosing
        upstream 400s (e.g., missing OpenRouter headers, invalid model).
        """

        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        provider = (settings.llm_provider or "openrouter").lower()
        if provider == "openrouter":
            if not settings.openrouter_api_key:
                raise HTTPException(status_code=400, detail="OPENROUTER_API_KEY missing")
            llm = ChatOpenAI(
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
                model=settings.default_model,
                temperature=0.0,
                default_headers={
                    "HTTP-Referer": settings.openrouter_http_referer,
                    "X-Title": settings.openrouter_x_title,
                },
            )
        elif provider == "ollama":
            llm = ChatOpenAI(
                api_key=getattr(settings, "ollama_api_key", None) or "ollama",
                base_url=getattr(settings, "ollama_base_url", None) or "http://localhost:11434/v1",
                model=settings.default_model,
                temperature=0.0,
            )
        else:
            if not settings.groq_api_key:
                raise HTTPException(status_code=400, detail="GROQ_API_KEY missing")
            llm = ChatOpenAI(
                api_key=settings.groq_api_key,
                base_url=settings.groq_base_url,
                model=settings.default_model,
                temperature=0.0,
            )

        try:
            msg = await llm.ainvoke([HumanMessage(content="Reply with exactly: ok")])
            return {
                "provider": provider,
                "model": settings.default_model,
                "reply": getattr(msg, "content", None),
            }
        except Exception as e:
            # Surface as much as we safely can.
            status = getattr(e, "status_code", None) or getattr(e, "status", None)
            detail = str(e)
            # If OpenAI SDK error, attempt to read response text.
            try:
                resp = getattr(e, "response", None)
                if resp is not None and hasattr(resp, "text"):
                    t = resp.text
                    if callable(t):
                        detail = t()
                    else:
                        detail = str(t)
            except Exception:
                pass
            raise HTTPException(status_code=502, detail={"status": status, "error": detail[:4000]})

    @app.get("/autonomous/status")
    async def autonomous_status():
        return corporation.status()

    @app.get("/autonomous/insights")
    async def autonomous_insights(limit: int = 25):
        bundles = insight_store.read_latest(limit=limit)
        # Return most-recent first
        return {"items": [b.model_dump() for b in bundles]}

    @app.get("/autonomous/jobs/recent")
    async def autonomous_jobs_recent(limit: int = 50):
        return {"items": scheduler.list_recent(limit=limit)}


    @app.post("/autonomous/flow/run-once")
    async def autonomous_flow_run_once(demo: bool = True):
        """Run a single end-to-end autonomous flow and return a trace.

        Useful for debugging the data flow between departments.
        """

        trace = await corporation.run_flow_once(demo=demo)
        # In demo mode, run verification/publish in-process so callers immediately
        # see a bundle appended to insights.jsonl (rather than waiting for the
        # background scheduler, which may be disabled).
        if demo:
            try:
                await corporation.run_verify_once_if_candidate_exists()
            except Exception as e:
                trace["verify_error"] = str(e)
        return trace

    @app.post("/autonomous/flow/run-once-real")
    async def autonomous_flow_run_once_real():
        """Run a single end-to-end autonomous flow in REAL mode (no demo fallbacks)."""

        # Surface missing keys early with a clear message.
        provider = (os.getenv("LLM_PROVIDER", "openrouter") or "openrouter").lower()
        key_missing = (
            (provider == "openrouter" and not os.getenv("OPENROUTER_API_KEY"))
            or (provider == "groq" and not os.getenv("GROQ_API_KEY"))
        )
        if key_missing:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"LLM API key missing for provider '{provider}'. "
                    "Set GROQ_API_KEY (for groq) or OPENROUTER_API_KEY (for openrouter), or call /autonomous/flow/run-once?demo=true. "
                    "(Ollama does not require an API key.)"
                ),
            )

        return await corporation.run_flow_once(demo=False)

    @app.post("/agent/run", response_model=AgentRunResponse)
    async def agent_run(req: AgentRunRequest):
        t0 = time.time()
        logging.getLogger("f1_agents.api").info(
            "agent_run_request namespace=%s msg_len=%s", req.namespace, len(req.message or "")
        )
        # Namespace can be inserted into system prompt if desired.
        extra = req.extra_system
        if req.namespace:
            ns_line = f"Knowledge-base namespace for this run: {req.namespace}."
            extra = (extra + "\n" if extra else "") + ns_line

        from .pipeline import run_pipeline

        result = await run_pipeline(
            settings=settings,
            kb=kb,
            agents_cache=agents_cache,
            agent_type=req.agent_type,
            user_message=req.message,
            namespace=req.namespace,
            extra_system=extra,
        )

        logging.getLogger("f1_agents.api").info(
            "agent_run_response namespace=%s duration_ms=%s answer_chars=%s tool_calls=%s",
            req.namespace,
            int((time.time() - t0) * 1000),
            len(result.get("answer") or ""),
            len(result.get("tool_calls") or []),
        )

        return AgentRunResponse(**result)

    return app


app = create_app()
