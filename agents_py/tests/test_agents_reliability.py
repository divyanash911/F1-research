from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage

from f1_agents_service.agent_graph import run_agent
from f1_agents_service.autonomous.corporation import _collect_follow_up_questions
from f1_agents_service.autonomous.specialist_agents import SpecialistFinding


class _DummyAgent:
    def __init__(self, messages):
        self._messages = messages

    async def ainvoke(self, _payload):
        return {"messages": self._messages}


def _finding(*, qid: str, follow_ups: list[str], allowed: bool = True) -> SpecialistFinding:
    return SpecialistFinding(
        question_id=qid,
        department="pace",
        question="q",
        answer_md="a",
        confidence=0.7,
        tags=["pace"],
        evidence=[],
        follow_up_questions=follow_ups,
        follow_up_allowed=allowed,
        exploration_depth=1,
        raw_tool_calls=[],
    )


def test_collect_follow_up_questions_filters_dedupes_and_honors_budget():
    findings = [
        _finding(qid="1", follow_ups=["  ", "How does tyre deg vary by stint in race trim?"], allowed=True),
        _finding(
            qid="2",
            follow_ups=[
                "How does tyre deg vary by stint in race trim?",
                "What is the effect of crosswinds in sector 2 for Ferrari?",
            ],
            allowed=True,
        ),
        _finding(qid="3", follow_ups=["Should be ignored"], allowed=False),
    ]

    got = _collect_follow_up_questions(findings, budget=2)

    assert got == [
        "How does tyre deg vary by stint in race trim?",
        "What is the effect of crosswinds in sector 2 for Ferrari?",
    ]


def test_run_agent_collects_tool_calls_from_message_field():
    tc = {"name": "web_search", "args": {"query": "f1 latest news"}, "id": "call-1"}
    dummy = _DummyAgent([AIMessage(content="", tool_calls=[tc]), AIMessage(content="done")])

    result = asyncio.run(run_agent(dummy, user_message="hello", extra_system=None))

    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["name"] == "web_search"


def test_run_agent_strict_grounding_raises(monkeypatch):
    dummy = _DummyAgent([AIMessage(content=""), AIMessage(content="See https://example.com/f1 for latest race results.")])
    monkeypatch.setenv("AGENTS_STRICT_GROUNDING", "1")

    try:
        raised = False
        try:
            asyncio.run(run_agent(dummy, user_message="latest race results", extra_system=None))
        except RuntimeError:
            raised = True
    finally:
        monkeypatch.delenv("AGENTS_STRICT_GROUNDING", raising=False)

    assert raised is True
