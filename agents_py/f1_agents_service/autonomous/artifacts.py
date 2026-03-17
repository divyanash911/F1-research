from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ArtifactRef:
    kind: str  # e.g. 'table', 'chart', 'document'
    path: str
    title: str | None = None
    metadata: dict[str, Any] | None = None


class ArtifactStore:
    """Stores generated artifacts (json, markdown, etc) on disk for the website."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_json(self, rel_path: str, obj: Any) -> ArtifactRef:
        p = self.root / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        return ArtifactRef(kind="json", path=str(p))

    def put_markdown(self, rel_path: str, md: str) -> ArtifactRef:
        p = self.root / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(md, encoding="utf-8")
        return ArtifactRef(kind="markdown", path=str(p))
