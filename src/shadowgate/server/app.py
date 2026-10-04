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


class RunRequest(BaseModel):
    runbook: str




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
        store.engine.on_job_result(req.job_id, req.ok)
        return {"status": "recorded"}

    @app.post("/runbooks")
    def register_runbook(body: dict[str, Any], store: Store = Depends(get_store)) -> dict[str, Any]:
        import json as _json

        from shadowgate.server.orchestrator import parse_runbook, validate

        spec = _json.dumps(body)
        runbook = parse_runbook(_json.dumps(body))
        errors = validate(runbook)
        if errors:
            raise HTTPException(status_code=400, detail=errors)
        store.engine.register_runbook(runbook, spec)
        return {"name": runbook.name, "steps": [s.name for s in runbook.steps]}

    @app.post("/runs")
    def start_run(req: RunRequest, store: Store = Depends(get_store)) -> dict[str, Any]:
        from shadowgate.server.orchestrator import parse_runbook

        spec = store.engine.get_runbook_spec(req.runbook)
        if spec is None:
            raise HTTPException(status_code=404, detail="unknown runbook")
        runbook = parse_runbook(spec)
        run_id = store.engine.start_run(runbook, store.list_agents())
        return {"run_id": run_id, "status": "running"}

    @app.get("/runs/{run_id}")
    def run_status(run_id: str, store: Store = Depends(get_store)) -> dict[str, Any]:
        status = store.engine.run_status(run_id)
        if status is None:
            raise HTTPException(status_code=404, detail="unknown run")
        return status

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

    from fastapi import Request
    from starlette.templating import Jinja2Templates

    templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "web" / "templates"))

    def render(request: Request, name: str, context: dict[str, Any]) -> Any:
        return templates.TemplateResponse(request, name, context)

    @app.get("/ui")
    def ui(request: Request) -> Any:
        return render(request, "agents.html", {"agents": store.list_agents()})

    @app.get("/ui/agents")
    def ui_agents(request: Request) -> Any:
        return render(request, "agents.html", {"agents": store.list_agents()})

    @app.get("/ui/jobs")
    def ui_jobs(request: Request) -> Any:
        return render(request, "jobs.html", {"stats": store.queue.stats()})

    @app.get("/ui/runs")
    def ui_runs(request: Request) -> Any:
        return render(request, "runs.html", {"runs": store.engine.list_runs()})

    return app


app = create_app()
