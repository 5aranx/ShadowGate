from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from shadowgate.config import Settings, get_settings
from shadowgate.server.audit import AuditLog
from shadowgate.server.store import Store


class EnrollRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    token: str
    tags: str = ""


class PollRequest(BaseModel):
    agent_id: str


class ResultRequest(BaseModel):
    job_id: str
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class JobRequest(BaseModel):
    agent_id: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(settings.audit_log_path)
    store = Store(settings.db_path, audit=audit)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        yield

    app = FastAPI(title="ShadowGate", lifespan=lifespan)
    app.state.store = store
    app.state.audit = audit

    def get_store() -> Store:
        store: Store = app.state.store
        return store

    def get_audit() -> AuditLog:
        audit: AuditLog = app.state.audit
        return audit

    @app.post("/tokens")
    def mint_token(store: Store = Depends(get_store)) -> dict[str, str]:
        return {"token": store.mint_token()}

    @app.post("/enroll")
    def enroll(req: EnrollRequest, store: Store = Depends(get_store)) -> dict[str, str]:
        if not store.burn_token(req.token, req.agent_id):
            raise HTTPException(status_code=403, detail="invalid or burned token")
        store.upsert_agent(req.agent_id, req.tags)
        store.audit.append("agent_enrolled", actor=req.agent_id, target="server",
                           detail={"tags": req.tags})
        return {"status": "enrolled", "agent_id": req.agent_id}

    @app.post("/jobs")
    def create_job(req: JobRequest, store: Store = Depends(get_store)) -> dict[str, str]:
        import uuid

        job_id = str(uuid.uuid4())
        store.queue.enqueue(job_id, req.agent_id, req.action, req.params)
        store.audit.append("job_enqueued", actor="operator", target=req.agent_id,
                           detail={"job_id": job_id, "action": req.action})
        return {"job_id": job_id, "status": "queued"}

    @app.post("/agent/poll")
    def agent_poll(req: PollRequest, store: Store = Depends(get_store)) -> dict[str, Any]:
        job = store.queue.claim_next(agent_id=req.agent_id)
        if job is None:
            return {"job": None}
        store.audit.append("job_claimed", actor=req.agent_id, target=job.id,
                           detail={"action": job.action})
        return {"job": {"id": job.id, "action": job.action, "params": job.params}}

    @app.post("/agent/result")
    def agent_result(req: ResultRequest, store: Store = Depends(get_store)) -> dict[str, str]:
        store.queue.complete(req.job_id, req.ok, req.data)
        store.audit.append("job_completed", actor="agent", target=req.job_id,
                           detail={"ok": req.ok, "error": req.error})
        return {"status": "recorded"}

    @app.get("/agents")
    def agents(store: Store = Depends(get_store)) -> dict[str, Any]:
        return {"agents": store.list_agents()}

    @app.get("/jobs")
    def jobs(store: Store = Depends(get_store)) -> dict[str, Any]:
        return {"stats": store.queue.stats()}

    @app.get("/audit")
    def audit_log(audit: AuditLog = Depends(get_audit), verify: bool = False) -> dict[str, Any]:
        return {"entries": audit.entries(), "verified": audit.verify_chain() if verify else None}

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
