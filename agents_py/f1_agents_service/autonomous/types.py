from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    openf1 = "openf1"
    web = "web"
    manual = "manual"


class EvidenceItem(BaseModel):
    source_type: SourceType
    source_id: str = Field(..., description="URL or an OpenF1 endpoint/query key")
    title: str | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    quote: str | None = Field(default=None, description="Short supporting excerpt")
    metadata: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    topic: str
    summary: str
    details_md: str = Field(default="")
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    tags: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class InsightBundle(BaseModel):
    run_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    kind: Literal[
        "news_digest",
        "race_preview",
        "telemetry_insight",
        "strategy_note",
        "upgrade_watch",
        "daily_brief",
    ]
    headline: str
    tldr: str
    findings: list[Finding] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
