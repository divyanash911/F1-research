from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class JobType(str, Enum):
    ingest_news = "ingest_news"
    next_race_context = "next_race_context"
    weather_update = "weather_update"
    telemetry_watch = "telemetry_watch"

    analyze_pace = "analyze_pace"
    analyze_telemetry = "analyze_telemetry"
    analyze_strategy = "analyze_strategy"

    verify_bundle = "verify_bundle"

    # analysis + publish
    daily_brief = "daily_brief"


@dataclass(frozen=True)
class JobSpec:
    job_type: JobType
    interval_seconds: int
    jitter_seconds: int = 5
    priority: int = 50


DEFAULT_JOBS: list[JobSpec] = [
    JobSpec(JobType.ingest_news, interval_seconds=15 * 60, priority=10),
    JobSpec(JobType.next_race_context, interval_seconds=6 * 60 * 60, priority=20),
    JobSpec(JobType.weather_update, interval_seconds=60 * 60, priority=30),
    JobSpec(JobType.telemetry_watch, interval_seconds=30 * 60, priority=40),

    JobSpec(JobType.analyze_pace, interval_seconds=2 * 60 * 60, priority=45),
    JobSpec(JobType.analyze_strategy, interval_seconds=3 * 60 * 60, priority=46),
    JobSpec(JobType.analyze_telemetry, interval_seconds=3 * 60 * 60, priority=47),

    JobSpec(JobType.daily_brief, interval_seconds=60 * 60, priority=50),
]
