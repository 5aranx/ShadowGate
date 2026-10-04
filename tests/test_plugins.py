from shadowgate.agent.executor import Executor
from shadowgate.plugins.base import Registry
from shadowgate.plugins.loader import load_builtins


def test_load_builtins_and_execute():
    reg = Registry()
    load_builtins(reg)
    assert set(reg.names()) == {"system_info", "file_fetch", "service_status", "disk_health"}

    ex = Executor(reg, agent_id="agent-1")
    res = ex.run("job-1", "system_info", {})
    assert res.ok is True
    assert "system" in res.data

    res = ex.run("job-2", "does_not_exist", {})
    assert res.ok is False
    assert "unknown action" in (res.error or "")
