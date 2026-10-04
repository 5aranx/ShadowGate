"""Run engine: materializes a runbook against live agents and advances it as
job results arrive. Concurrency is capped per run; a failed step fails the run
and enqueues its compensating steps.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from typing import Any

from shadowgate.server.audit import AuditLog
from shadowgate.server.orchestrator import Runbook, Step, matches, topo_order
from shadowgate.server.queue import SqlQueue


class RunEngine:
    def __init__(self, conn: sqlite3.Connection, queue: SqlQueue, audit: AuditLog) -> None:
        self._conn = conn
        self.queue = queue
        self.audit = audit
        self._setup()

    def _setup(self) -> None:
        with closing(self._conn.cursor()) as cur:
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS runbooks(name TEXT PRIMARY KEY, spec TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, runbook TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS run_steps(run_id TEXT NOT NULL, step TEXT NOT NULL,
                    status TEXT NOT NULL, PRIMARY KEY(run_id, step));
                CREATE TABLE IF NOT EXISTS run_step_agents(run_id TEXT NOT NULL, step TEXT NOT NULL,
                    agent_id TEXT NOT NULL, status TEXT NOT NULL,
                    PRIMARY KEY(run_id, step, agent_id));
                CREATE TABLE IF NOT EXISTS run_jobs(job_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    step TEXT NOT NULL, agent_id TEXT NOT NULL);
                """
            )
        self._conn.commit()

    def register_runbook(self, runbook: Runbook, spec: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO runbooks(name,spec) VALUES(?,?)", (runbook.name, spec)
        )
        self._conn.commit()

    def get_runbook_spec(self, name: str) -> str | None:
        row = self._conn.execute("SELECT spec FROM runbooks WHERE name=?", (name,)).fetchone()
        return row[0] if row else None

    def start_run(self, runbook: Runbook, agents: list[dict[str, Any]]) -> str:
        run_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "INSERT INTO runs(id,runbook,status,created_at) VALUES(?,?,'running',?)",
            (run_id, runbook.name, now),
        )
        for step in runbook.steps:
            initial = "skipped" if step.compensate_for is not None else "pending"
            self._conn.execute(
                "INSERT INTO run_steps(run_id,step,status) VALUES(?,?,?)",
                (run_id, step.name, initial),
            )
            if step.compensate_for is not None:
                continue
            for agent in agents:
                if matches(step, str(agent.get("tags", ""))):
                    self._conn.execute(
                        "INSERT INTO run_step_agents(run_id,step,agent_id,status)"
                        " VALUES(?,?,?,'pending')",
                        (run_id, step.name, agent["id"]),
                    )
        self._conn.commit()
        self.audit.append("run_started", actor="operator", target=run_id,
                          detail={"runbook": runbook.name})
        for name in topo_order(runbook):
            root_step = runbook.step(name)
            assert root_step is not None
            if root_step.compensate_for is None and not root_step.depends_on:
                self._schedule(run_id, root_step, runbook, agents)
        return run_id

    def _running_count(self, run_id: str) -> int:
        return int(self._conn.execute(
            "SELECT COUNT(*) FROM run_step_agents WHERE run_id=? AND status='running'",
            (run_id,),
        ).fetchone()[0])

    def _schedule(self, run_id: str, step: Step, runbook: Runbook,
                  agents: list[dict[str, Any]]) -> None:
        capacity = max(0, runbook.max_concurrent - self._running_count(run_id))
        if capacity == 0:
            return
        rows = self._conn.execute(
            "SELECT agent_id FROM run_step_agents WHERE run_id=? AND step=? AND status='pending' "
            "ORDER BY rowid LIMIT ?",
            (run_id, step.name, capacity),
        ).fetchall()
        if not rows:
            return
        self._conn.execute(
            "UPDATE run_steps SET status='running' WHERE run_id=? AND step=? AND status='pending'",
            (run_id, step.name),
        )
        for (agent_id,) in rows:
            job_id = str(uuid.uuid4())
            self.queue.enqueue(job_id, agent_id, step.action, step.params)
            self._conn.execute(
                "UPDATE run_step_agents SET status='running'"
                " WHERE run_id=? AND step=? AND agent_id=?",
                (run_id, step.name, agent_id),
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO run_jobs(job_id,run_id,step,agent_id) VALUES(?,?,?,?)",
                (job_id, run_id, step.name, agent_id),
            )
            self.audit.append("job_enqueued", actor="runbook", target=agent_id,
                              detail={"job_id": job_id, "action": step.action, "run": run_id})
        self._conn.commit()

    def on_job_result(self, job_id: str, ok: bool) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT run_id, step, agent_id FROM run_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        run_id, step_name, aid = row
        new_status = "done" if ok else "failed"
        self._conn.execute(
            "UPDATE run_step_agents SET status=? WHERE run_id=? AND step=? AND agent_id=?",
            (new_status, run_id, step_name, aid),
        )
        self._conn.execute("DELETE FROM run_jobs WHERE job_id=?", (job_id,))
        run_row = self._conn.execute("SELECT runbook FROM runs WHERE id=?", (run_id,)).fetchone()
        self._conn.commit()
        if not ok:
            self._fail_run(run_id, run_row[0] if run_row else "")
            return {"run_id": run_id, "status": "failed"}
        self._maybe_advance(run_id, run_row[0] if run_row else "")
        return {"run_id": run_id, "status": "ok"}

    def _maybe_advance(self, run_id: str, runbook_name: str) -> None:
        current = self._conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
        if current is None or current[0] != "running":
            return
        spec = self.get_runbook_spec(runbook_name)
        if spec is None:
            return
        from shadowgate.server.orchestrator import parse_runbook

        runbook = parse_runbook(spec)
        agents = self._agents_for_run(run_id)
        # fill capacity for any running steps
        for step in runbook.steps:
            if step.compensate_for is not None:
                continue
            self._schedule(run_id, step, runbook, agents)
        # close out finished steps, open dependents
        for step in runbook.steps:
            if step.compensate_for is not None:
                continue
            row = self._conn.execute(
                "SELECT status FROM run_steps WHERE run_id=? AND step=?", (run_id, step.name)
            ).fetchone()
            if row and row[0] == "running":
                remaining = self._conn.execute(
                    "SELECT COUNT(*) FROM run_step_agents WHERE run_id=? AND step=? "
                    "AND status IN ('pending','running')",
                    (run_id, step.name),
                ).fetchone()[0]
                if remaining == 0:
                    failed = self._conn.execute(
                        "SELECT COUNT(*) FROM run_step_agents WHERE run_id=? AND step=?"
                        " AND status='failed'",
                        (run_id, step.name),
                    ).fetchone()[0]
                    self._conn.execute(
                        "UPDATE run_steps SET status=? WHERE run_id=? AND step=?",
                        ("failed" if failed else "done", run_id, step.name),
                    )
                    self._conn.commit()
                    if failed:
                        self._fail_run(run_id, runbook_name)
                        return
            if row and row[0] == "pending":
                deps_done = all(
                    (self._conn.execute(
                        "SELECT status FROM run_steps WHERE run_id=? AND step=?", (run_id, d)
                    ).fetchone() or (None,))[0] == "done"
                    for d in step.depends_on
                )
                if deps_done:
                    self._schedule(run_id, step, runbook, agents)
        # run done?
        not_done = self._conn.execute(
            "SELECT COUNT(*) FROM run_steps WHERE run_id=? AND status IN ('pending','running')",
            (run_id,),
        ).fetchone()[0]
        if not_done == 0:
            self._conn.execute("UPDATE runs SET status='done' WHERE id=?", (run_id,))
            self._conn.commit()
            self.audit.append("run_completed", actor="engine", target=run_id, detail={})

    def _agents_for_run(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT DISTINCT agent_id FROM run_step_agents WHERE run_id=?", (run_id,)
        ).fetchall()
        out: list[dict[str, Any]] = []
        for (aid,) in rows:
            tag_row = self._conn.execute("SELECT tags FROM agents WHERE id=?", (aid,)).fetchone()
            out.append({"id": aid, "tags": tag_row[0] if tag_row else ""})
        return out

    def _fail_run(self, run_id: str, runbook_name: str) -> None:
        self._conn.execute("UPDATE runs SET status='failed' WHERE id=?", (run_id,))
        self._conn.commit()
        self.audit.append("run_failed", actor="engine", target=run_id, detail={})
        spec = self.get_runbook_spec(runbook_name)
        if spec is None:
            return
        from shadowgate.server.orchestrator import parse_runbook

        runbook = parse_runbook(spec)
        for step in runbook.steps:
            if step.compensate_for is None:
                continue
            failed_step = runbook.step(step.compensate_for)
            if failed_step is None:
                continue
            self._conn.execute(
                "UPDATE run_steps SET status='done' WHERE run_id=? AND step=?",
                (run_id, step.name),
            )
            targets = self._conn.execute(
                "SELECT agent_id FROM run_step_agents WHERE run_id=? AND step=?",
                (run_id, failed_step.name),
            ).fetchall()
            for (agent_id,) in targets:
                job_id = str(uuid.uuid4())
                self.queue.enqueue(job_id, agent_id, step.action, step.params)
                self._conn.execute(
                    "INSERT OR REPLACE INTO run_jobs(job_id,run_id,step,agent_id) VALUES(?,?,?,?)",
                    (job_id, run_id, step.name, agent_id),
                )
                self.audit.append("compensation_enqueued", actor="engine", target=agent_id,
                                  detail={"job_id": job_id, "action": step.action, "run": run_id})
        self._conn.commit()

    def run_status(self, run_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id,runbook,status FROM runs WHERE id=?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        steps = self._conn.execute(
            "SELECT step,status FROM run_steps WHERE run_id=?", (run_id,)
        ).fetchall()
        return {"id": row[0], "runbook": row[1], "status": row[2], "steps": dict(steps)}
