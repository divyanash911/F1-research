from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class KVRow:
    key: str
    value: dict[str, Any]
    updated_at: str


class StateStore:
    """Small persistent KV store (sqlite) for department outputs.

    Use this to persist:
    - latest news signals
    - latest next-race context
    - latest weather summary
    - latest telemetry summaries

    The publisher job reads these and synthesizes an InsightBundle.
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
                CREATE TABLE IF NOT EXISTS kv (
                    k TEXT PRIMARY KEY,
                    v TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def set(self, key: str, value: dict[str, Any]) -> None:
        with self._connect() as c:
            c.execute(
                "INSERT INTO kv(k,v,updated_at) VALUES(?,?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_at=excluded.updated_at",
                (key, json.dumps(value, ensure_ascii=False), _utc_iso()),
            )

    def get(self, key: str) -> KVRow | None:
        with self._connect() as c:
            row = c.execute("SELECT k,v,updated_at FROM kv WHERE k=?", (key,)).fetchone()
        if not row:
            return None
        return KVRow(key=str(row["k"]), value=json.loads(row["v"]), updated_at=str(row["updated_at"]))

    def dump(self) -> list[KVRow]:
        with self._connect() as c:
            rows = c.execute("SELECT k,v,updated_at FROM kv ORDER BY k ASC").fetchall()
        out: list[KVRow] = []
        for r in rows:
            out.append(KVRow(key=str(r["k"]), value=json.loads(r["v"]), updated_at=str(r["updated_at"])))
        return out
