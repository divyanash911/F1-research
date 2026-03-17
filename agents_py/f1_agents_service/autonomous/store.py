from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from .types import InsightBundle


class InsightStore:
    """A tiny append-only JSONL store for generated insight bundles.

    This is intentionally simple and local-first so the agent loop can run
    without any external DB.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def append(self, bundle: InsightBundle) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(bundle.model_dump_json())
            f.write("\n")
            # Make append visible immediately for short-lived processes.
            f.flush()
            os.fsync(f.fileno())

    def read_latest(self, limit: int = 50) -> list[InsightBundle]:
        if limit <= 0:
            return []
        if not self.path.exists():
            return []

        # Efficient-ish tail for JSONL; file sizes here are expected to be small.
        lines: list[str] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
        lines = lines[-limit:]
        out: list[InsightBundle] = []
        for ln in reversed(lines):
            try:
                out.append(InsightBundle.model_validate_json(ln))
            except Exception:
                continue
        return out

    def iter_bundles(self) -> Iterable[InsightBundle]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield InsightBundle.model_validate_json(line)
                except Exception:
                    continue
