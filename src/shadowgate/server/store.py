"""Single sqlite store (WAL) for agents, enrollment tokens, and job state.

All writes go through one module so enrollment-token burn and job claim share
transactional semantics with the audit hash chain.
"""

from __future__ import annotations

import secrets
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from shadowgate.server.audit import AuditLog
from shadowgate.server.queue import SqlQueue


class Store:
    def __init__(self, path: str, audit: AuditLog | None = None) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._setup()
        self.queue = SqlQueue(path)
        self.audit: AuditLog = audit or AuditLog(str(Path(path).parent / "audit.log"))

    def _setup(self) -> None:
        with closing(self._conn.cursor()) as cur:
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents(
                    id TEXT PRIMARY KEY,
                    tags TEXT NOT NULL DEFAULT '',
                    enrolled_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS enroll_tokens(
                    token TEXT PRIMARY KEY,
                    minted_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    burned_at TEXT,
                    agent_id TEXT
                );
                """
            )
        self._conn.commit()

    def mint_token(self, ttl_minutes: int = 30) -> str:
        token = secrets.token_urlsafe(24)
        minted = datetime.now(UTC)
        expires = minted + timedelta(minutes=ttl_minutes)
        self._conn.execute(
            "INSERT INTO enroll_tokens(token,minted_at,expires_at) VALUES(?,?,?)",
            (token, minted.isoformat(), expires.isoformat()),
        )
        self._conn.commit()
        return token

    def burn_token(self, token: str, agent_id: str) -> bool:
        cur = self._conn.execute(
            "UPDATE enroll_tokens SET burned_at=?, agent_id=? "
            "WHERE token=? AND burned_at IS NULL AND expires_at > ?",
            (
                datetime.now(UTC).isoformat(),
                agent_id,
                token,
                datetime.now(UTC).isoformat(),
            ),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def upsert_agent(self, agent_id: str, tags: str = "") -> None:
        self._conn.execute(
            "INSERT INTO agents(id,tags,enrolled_at) VALUES(?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET tags=excluded.tags",
            (agent_id, tags, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()

    def list_agents(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT id,tags,enrolled_at FROM agents").fetchall()
        return [{"id": r[0], "tags": r[1], "enrolled_at": r[2]} for r in rows]

    def enrollment_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0])
