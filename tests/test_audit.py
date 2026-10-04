from shadowgate.server.audit import AuditLog


def test_chain_verifies_and_tamper_detected(tmp_path):
    log = AuditLog(tmp_path / "audit.log")
    log.append("job_enqueued", actor="admin", target="agent-1", detail={"action": "system_info"})
    log.append("agent_enrolled", actor="agent-1", target="server")
    log.append("job_completed", actor="agent-1", target="job-1", detail={"ok": True})

    assert log.verify_chain() is True

    # tamper with an entry
    lines = (tmp_path / "audit.log").read_text().splitlines()
    entry = __import__("json").loads(lines[1])
    entry["detail"] = {"ok": False}
    lines[1] = __import__("json").dumps(entry)
    (tmp_path / "audit.log").write_text("\n".join(lines) + "\n")

    assert log.verify_chain() is False
