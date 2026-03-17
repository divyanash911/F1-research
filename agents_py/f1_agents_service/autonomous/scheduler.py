from __future__ import annotations

import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .jobs import JobSpec, JobType


def _utc_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DueJob:
    id: str
    job_type: JobType
    scheduled_at: str
    attempts: int


class JobScheduler:
    """Very small persistent scheduler.

    - Uses sqlite for durability (no external services)
    - Provides a leasing mechanism to avoid duplicate work
    - Stores success/failure history

    This is intentionally minimal and easy to reason about.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init(self) -> None:
        with self._connect() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_until TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_due ON jobs(status, scheduled_at)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type, status, scheduled_at)"
            )

    def seed_periodic_jobs(self, specs: list[JobSpec]) -> None:
        """Ensure there is at least one pending job per periodic spec."""
        now = _utc_ts()
        with self._connect() as c:
            for spec in specs:
                row = c.execute(
                    "SELECT id FROM jobs WHERE job_type=? AND status IN ('pending','leased') ORDER BY scheduled_at DESC LIMIT 1",
                    (spec.job_type.value,),
                ).fetchone()
                if row:
                    continue
                self.enqueue(spec.job_type, scheduled_at=now)

    def enqueue(self, job_type: JobType, scheduled_at: str | None = None) -> str:
        jid = uuid.uuid4().hex
        scheduled_at = scheduled_at or _utc_ts()
        with self._connect() as c:
            c.execute(
                "INSERT INTO jobs(id,job_type,scheduled_at,status,created_at) VALUES(?,?,?,?,?)",
                (jid, job_type.value, scheduled_at, "pending", _utc_ts()),
            )
        return jid

    def lease_next(self, owner: str, lease_seconds: int = 300) -> DueJob | None:
        """Lease the next due job (pending and scheduled_at <= now)."""
        now = _utc_ts()
        lease_until = datetime.now(timezone.utc).timestamp() + lease_seconds
        lease_until_iso = datetime.fromtimestamp(lease_until, tz=timezone.utc).isoformat()

        with self._connect() as c:
            # Release expired leases
            c.execute(
                "UPDATE jobs SET status='pending', lease_owner=NULL, lease_until=NULL WHERE status='leased' AND lease_until <= ?",
                (now,),
            )

            row = c.execute(
                """
                SELECT id, job_type, scheduled_at, attempts
                FROM jobs
                WHERE status='pending' AND scheduled_at <= ?
                ORDER BY scheduled_at ASC
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if not row:
                return None

            jid = row["id"]
            updated = c.execute(
                """
                UPDATE jobs
                SET status='leased', lease_owner=?, lease_until=?
                WHERE id=? AND status='pending'
                """,
                (owner, lease_until_iso, jid),
            )
            if updated.rowcount != 1:
                return None

            return DueJob(
                id=jid,
                job_type=JobType(str(row["job_type"])),
                scheduled_at=str(row["scheduled_at"]),
                attempts=int(row["attempts"]),
            )

    def mark_success(self, job_id: str) -> None:
        with self._connect() as c:
            c.execute(
                "UPDATE jobs SET status='done', lease_owner=NULL, lease_until=NULL, last_error=NULL WHERE id=?",
                (job_id,),
            )

    def mark_failure(self, job_id: str, error: str, backoff_seconds: int = 120) -> None:
        # requeue with backoff; cap attempts loosely
        scheduled_at = datetime.fromtimestamp(time.time() + backoff_seconds, tz=timezone.utc).isoformat()
        with self._connect() as c:
            c.execute(
                """
                UPDATE jobs
                SET status='pending', lease_owner=NULL, lease_until=NULL,
                    attempts=attempts+1, last_error=?, scheduled_at=?
                WHERE id=?
                """,
                (error[:5000], scheduled_at, job_id),
            )

    def list_recent(self, limit: int = 50) -> list[dict]:
        with self._connect() as c:
            rows = c.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
