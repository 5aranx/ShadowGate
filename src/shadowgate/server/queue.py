"""DB-backed queue with atomic, exactly-once claim via UPDATE ... RETURNING."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass
class ClaimedJob:
    id: str
    action: str
    params: dict[str, Any]


class SqlQueue:
    """Synchronous SQLite queue for correctness tests; the async wrapper is a
    thin coroutine around the same pattern. Atomicity comes from a single
    UPDATE constrained to status='queued'."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._setup()

    def _setup(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS qjobs(
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                action TEXT NOT NULL,
                params TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'queued'
            );
            CREATE INDEX IF NOT EXISTS idx_qjobs_status ON qjobs(status);
            """
        )
        self._conn.commit()

    def enqueue(self, job_id: str, agent_id: str, action: str, params: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO qjobs(id,agent_id,action,params,status) VALUES(?,?,?,?,'queued')",
            (job_id, agent_id, action, json.dumps(params)),
        )
        self._conn.commit()

    def claim_next(self) -> ClaimedJob | None:
        cur = self._conn.execute(
            """
            UPDATE qjobs SET status='running'
            WHERE id = (SELECT id FROM qjobs WHERE status='queued' ORDER BY rowid LIMIT 1)
            RETURNING id, action, params
            """
        )
        row = cur.fetchone()
        self._conn.commit()
        if row is None:
            return None
        return ClaimedJob(id=row[0], action=row[1], params=json.loads(row[2]))

    def complete(self, job_id: str, ok: bool, data: dict[str, Any]) -> None:
        self._conn.execute(
            "UPDATE qjobs SET status=? WHERE id=?",
            ("done" if ok else "failed", job_id),
        )
        self._conn.commit()

    def stats(self) -> dict[str, int]:
        rows = self._conn.execute("SELECT status, COUNT(*) FROM qjobs GROUP BY status").fetchall()
        return {status: count for status, count in rows}
