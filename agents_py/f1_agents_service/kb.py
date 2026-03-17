from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


@dataclass
class KBRecord:
    """A small append-only memory record."""

    ts: str
    namespace: str
    text: str
    metadata: dict[str, Any]


class JsonlKnowledgeBase:
    """A dead-simple long-term memory store.

    - append-only JSONL
    - naive keyword search

    This is intentionally simple and dependency-free; you can later swap in a vector DB.
    """

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def add(self, namespace: str, text: str, metadata: dict[str, Any] | None = None) -> KBRecord:
        rec = KBRecord(
            ts=datetime.utcnow().isoformat() + "Z",
            namespace=namespace,
            text=text,
            metadata=metadata or {},
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec.__dict__, ensure_ascii=False) + "\n")
        return rec

    def iter_records(self) -> Iterable[KBRecord]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    yield KBRecord(
                        ts=str(obj.get("ts", "")),
                        namespace=str(obj.get("namespace", "default")),
                        text=str(obj.get("text", "")),
                        metadata=dict(obj.get("metadata", {}) or {}),
                    )
                except json.JSONDecodeError:
                    continue

    def search(self, query: str, namespace: str | None = None, limit: int = 8) -> list[KBRecord]:
        q = query.lower().strip()
        if not q:
            return []

        scored: list[tuple[int, KBRecord]] = []
        for rec in self.iter_records():
            if namespace and rec.namespace != namespace:
                continue
            hay = (rec.text + " " + json.dumps(rec.metadata, ensure_ascii=False)).lower()
            score = hay.count(q)
            if score > 0:
                scored.append((score, rec))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]
