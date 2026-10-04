import pytest
from fastapi.testclient import TestClient

from shadowgate.config import Settings
from shadowgate.server.app import create_app

TOKENS = '{"tok-admin":"admin","tok-op":"operator","tok-view":"viewer"}'


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        db_path=str(tmp_path / "sg.db"),
        data_dir=str(tmp_path / "data"),
        audit_log_path=str(tmp_path / "audit.log"),
        org_key_path=str(tmp_path / "org.key"),
        ca_key_path=str(tmp_path / "ca.key"),
        ca_cert_path=str(tmp_path / "ca.crt"),
        api_tokens_json=TOKENS,
    )
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def test_viewer_can_read_not_write(client):
    r = client.get("/agents", headers=_h("tok-view"))
    assert r.status_code == 200
    r = client.post(
        "/jobs", json={"agent_id": "a", "action": "system_info"}, headers=_h("tok-view")
    )
    assert r.status_code == 403


def test_operator_runs_not_mints(client):
    r = client.post("/jobs", json={"agent_id": "a", "action": "system_info"}, headers=_h("tok-op"))
    assert r.status_code == 200
    r = client.post("/tokens", headers=_h("tok-op"))
    assert r.status_code == 403


def test_admin_mints(client):
    r = client.post("/tokens", headers=_h("tok-admin"))
    assert r.status_code == 200


def test_missing_or_bad_token_is_401(client):
    r = client.get("/agents")
    assert r.status_code == 401
    r = client.get("/agents", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_rate_limit_on_tokens(tmp_path):
    settings = Settings(
        db_path=str(tmp_path / "sg.db"),
        data_dir=str(tmp_path / "data"),
        audit_log_path=str(tmp_path / "audit.log"),
        org_key_path=str(tmp_path / "org.key"),
        ca_key_path=str(tmp_path / "ca.key"),
        ca_cert_path=str(tmp_path / "ca.crt"),
        api_tokens_json=TOKENS,
        rate_limit_per_minute=2,
    )
    app = create_app(settings)
    with TestClient(app) as c:
        assert c.post("/tokens", headers=_h("tok-admin")).status_code == 200
        assert c.post("/tokens", headers=_h("tok-admin")).status_code == 200
        r = c.post("/tokens", headers=_h("tok-admin"))
        assert r.status_code == 429
