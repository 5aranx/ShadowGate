import pytest
from fastapi.testclient import TestClient

from shadowgate.config import Settings
from shadowgate.server.app import create_app


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


def test_enroll_token_burned_once(client):
    token = client.post("/tokens").json()["token"]
    r1 = client.post("/enroll", json={"agent_id": "a1", "token": token, "tags": "linux,lab"})
    assert r1.status_code == 200
    r2 = client.post("/enroll", json={"agent_id": "a2", "token": token})
    assert r2.status_code == 403


def test_job_lifecycle_and_audit(client):
    token = client.post("/tokens").json()["token"]
    client.post("/enroll", json={"agent_id": "a1", "token": token, "tags": "linux"})
    jid = client.post("/jobs", json={"agent_id": "a1", "action": "system_info"}).json()["job_id"]

    poll = client.post("/agent/poll", json={"agent_id": "a1"}).json()
    assert poll["job"] is not None
    assert poll["job"]["id"] == jid
    assert poll["job"]["action"] == "system_info"

    res = client.post(
        "/agent/result", json={"job_id": jid, "ok": True, "data": {"system": "Linux"}}
    )
    assert res.status_code == 200

    stats = client.get("/jobs").json()["stats"]
    assert stats.get("done") == 1

    audit = client.get("/audit", params={"verify": True}).json()
    assert audit["verified"] is True
    events = [e["event"] for e in audit["entries"]]
    assert events == ["agent_enrolled", "job_enqueued", "job_claimed", "job_completed"]


def test_poll_only_claims_own_jobs(client):
    t1 = client.post("/tokens").json()["token"]
    t2 = client.post("/tokens").json()["token"]
    client.post("/enroll", json={"agent_id": "a1", "token": t1})
    client.post("/enroll", json={"agent_id": "a2", "token": t2})
    client.post("/jobs", json={"agent_id": "a1", "action": "system_info"})
    poll = client.post("/agent/poll", json={"agent_id": "a2"}).json()
    assert poll["job"] is None
    poll = client.post("/agent/poll", json={"agent_id": "a1"}).json()
    assert poll["job"] is not None
