from __future__ import annotations

from pathlib import Path

from f1_agents_service.autonomous.corporation import F1ResearchCorporation
from f1_agents_service.autonomous.scheduler import JobScheduler
from f1_agents_service.autonomous.store import InsightStore
from f1_agents_service.kb import JsonlKnowledgeBase
from f1_agents_service.settings import Settings


def test_run_flow_once_demo_appends_insight(tmp_path: Path, monkeypatch):
    """Demo flow should create + publish at least one InsightBundle.

    This protects against regressions where department work happens but nothing
    is appended to insights.jsonl (common when background workers are disabled).
    """

    # Force demo mode and disable autonomous background workers.
    monkeypatch.setenv("CORP_DEMO_MODE", "1")
    monkeypatch.setenv("AUTONOMOUS_ENABLED", "0")

    store_path = tmp_path / "insights.jsonl"
    sched_path = tmp_path / "jobs.sqlite"
    state_path = tmp_path / "state.sqlite"
    artifacts_dir = tmp_path / "artifacts"

    monkeypatch.setenv("AUTONOMOUS_STORE_PATH", str(store_path))
    monkeypatch.setenv("AUTONOMOUS_SCHEDULER_DB", str(sched_path))
    monkeypatch.setenv("AUTONOMOUS_STATE_DB", str(state_path))
    monkeypatch.setenv("AUTONOMOUS_ARTIFACTS_DIR", str(artifacts_dir))

    settings = Settings(llm_provider="groq", groq_api_key=None)
    kb = JsonlKnowledgeBase(str(tmp_path / "kb.jsonl"))

    scheduler = JobScheduler(str(sched_path))
    store = InsightStore(str(store_path))

    corp = F1ResearchCorporation(settings=settings, kb=kb, scheduler=scheduler, store=store)

    # run_flow_once in demo mode creates a candidate, then we publish in-process.
    import asyncio

    asyncio.run(corp.run_flow_once(demo=True))
    published = asyncio.run(corp.run_verify_once_if_candidate_exists())

    assert published is True
    assert store_path.exists()
    assert store_path.read_text(encoding="utf-8").strip() != ""

    bundles = store.read_latest(limit=10)
    assert len(bundles) >= 1
    # v2 corporation emits a structured prediction finding in demo mode, which
    # upgrades the published bundle kind to a race preview.
    assert bundles[0].kind in {"daily_brief", "race_preview"}
