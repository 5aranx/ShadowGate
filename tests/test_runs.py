import pytest
from fastapi.testclient import TestClient

from shadowgate.config import Settings
from shadowgate.server.app import create_app

RUNBOOK = {
    "name": "demo",
    "max_concurrent": 2,
    "steps": [
        {"name": "inventory", "action": "system_info", "targets": {"tag": "linux"}},
        {
            "name": "disk",
            "action": "disk_health",
            "targets": {"tag": "linux"},
            "depends_on": ["inventory"],
        },
        {
            "name": "compensate-disk",
            "action": "disk_health",
            "targets": {"tag": "linux"},
            "compensate_for": "disk",
        },
    ],
}


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        db_path=str(tmp_path / "sg.db"),
        data_dir=str(tmp_path / "data"),
        audit_log_path=str(tmp_path / "audit.log"),
        org_key_path=str(tmp_path / "org.key"),
        ca_key_path=str(tmp_path / "ca.key"),
        ca_cert_path=str(tmp_path / "ca.crt"),
    )
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def _enroll(client, agent_id, tags):
    token = client.post("/tokens").json()["token"]
    client.post("/enroll", json={"agent_id": agent_id, "token": token, "tags": tags})


def test_run_fanout_ordering_and_audit(client):
    _enroll(client, "a1", "linux")
    _enroll(client, "a2", "linux")
    r = client.post("/runbooks", json=RUNBOOK)
    assert r.status_code == 200
    run_id = client.post("/runs", json={"runbook": "demo"}).json()["run_id"]

    # first wave: inventory for a1 and a2 (max_concurrent=2, so no more)
    for agent in ("a1", "a2"):
        job = client.post("/agent/poll", json={"agent_id": agent}).json()["job"]
        assert job is not None and job["action"] == "system_info"
        client.post("/agent/result", json={"job_id": job["id"], "ok": True})

    # disk step should now be enqueued for both
    for agent in ("a1", "a2"):
        job = client.post("/agent/poll", json={"agent_id": agent}).json()["job"]
        assert job is not None and job["action"] == "disk_health"
        client.post("/agent/result", json={"job_id": job["id"], "ok": True})

    status = client.get(f"/runs/{run_id}").json()
    assert status["status"] == "done"
    assert status["steps"] == {
        "inventory": "done",
        "disk": "done",
        "compensate-disk": "skipped",
    }

    audit = client.get("/audit", params={"verify": True}).json()
    assert audit["verified"] is True


def test_failure_triggers_compensation(client):
    _enroll(client, "a1", "linux")
    client.post("/runbooks", json=RUNBOOK)
    run_id = client.post("/runs", json={"runbook": "demo"}).json()["run_id"]

    job = client.post("/agent/poll", json={"agent_id": "a1"}).json()["job"]
    client.post("/agent/result", json={"job_id": job["id"], "ok": True})

    # disk step now queued; fail it
    job = client.post("/agent/poll", json={"agent_id": "a1"}).json()["job"]
    assert job["action"] == "disk_health"
    client.post("/agent/result", json={"job_id": job["id"], "ok": False})

    status = client.get(f"/runs/{run_id}").json()
    assert status["status"] == "failed"

    # compensation job for disk should be claimable
    job = client.post("/agent/poll", json={"agent_id": "a1"}).json()["job"]
    assert job is not None and job["action"] == "disk_health"

    events = [e["event"] for e in client.get("/audit").json()["entries"]]
    assert "compensation_enqueued" in events
    assert "run_failed" in events
