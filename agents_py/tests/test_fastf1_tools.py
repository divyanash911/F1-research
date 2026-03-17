from __future__ import annotations

import os

import pytest


@pytest.mark.parametrize("tool_name", [
    "fastf1_event_schedule",
])
def test_fastf1_tools_import(tool_name: str):
    # Importing tools should not error even if FastF1 isn't installed yet in CI.
    # (If FastF1 is installed, tools will fully work.)
    from f1_agents_service import tools_fastf1  # noqa: F401

    assert hasattr(tools_fastf1, tool_name)
