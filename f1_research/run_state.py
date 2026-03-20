"""run_state.py

Lightweight persistence layer so CrewAI runs don't lose progress.

CrewAI will re-run a full crew when an exception happens mid-flight. This file
adds a minimal checkpoint/resume mechanism at the *task boundary*:

- After each Task completes, we write its output to disk (JSON).
- On retry (or rerun), we can skip already completed tasks.

This doesn't require patching CrewAI internals and keeps the logic in our own
orchestrator.

Contract
- Key: (session_id, crew_name)
- Persists: per-task status and text output
- Safe writes: atomic replace
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def _sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name).strip("_")


@dataclass
class TaskCheckpoint:
    index: int
    description_preview: str
    agent_role: str
    output: str
    had_preloaded_memory: bool = False
    preloaded_memory_preview: str = ""
    tools_used: list[str] | None = None


class RunState:
    def __init__(self, base_dir: Path, session_id: str, crew_name: str):
        self.base_dir = base_dir
        self.session_id = session_id
        self.crew_name = crew_name
        self.state_path = base_dir / session_id / f"run_state_{_sanitize(crew_name)}.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = {"session_id": session_id, "crew": crew_name, "tasks": []}
        self._load()

    def _load(self) -> None:
        if self.state_path.exists():
            try:
                self._data = json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                # If the file is corrupt, keep going with an empty state
                self._data = {"session_id": self.session_id, "crew": self.crew_name, "tasks": []}

    def _atomic_write(self, payload: dict[str, Any]) -> None:
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def mark_task_complete(self, checkpoint: TaskCheckpoint) -> None:
        tasks: list[dict[str, Any]] = list(self._data.get("tasks", []))
        tasks.append(
            {
                "index": checkpoint.index,
                "description_preview": checkpoint.description_preview,
                "agent_role": checkpoint.agent_role,
                "output": checkpoint.output,
                "had_preloaded_memory": checkpoint.had_preloaded_memory,
                "preloaded_memory_preview": checkpoint.preloaded_memory_preview,
                "tools_used": list(checkpoint.tools_used or []),
            }
        )
        self._data["tasks"] = tasks
        self._atomic_write(self._data)

    def completed_task_count(self) -> int:
        return len(self._data.get("tasks", []))

    def completed_tasks(self) -> list[dict[str, Any]]:
        return list(self._data.get("tasks", []))

    def task_output(self, index: int) -> Optional[str]:
        for t in self._data.get("tasks", []):
            if t.get("index") == index:
                return t.get("output")
        return None

    def clear(self) -> None:
        self._data = {"session_id": self.session_id, "crew": self.crew_name, "tasks": []}
        self._atomic_write(self._data)
