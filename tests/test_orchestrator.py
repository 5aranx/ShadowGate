import pytest

from shadowgate.server.orchestrator import parse_runbook, topo_order, validate

VALID = """
name: demo
max_concurrent: 2
steps:
  - name: inventory
    action: system_info
    targets: {tag: linux}
  - name: disk
    action: disk_health
    targets: {tag: linux}
    depends_on: [inventory]
"""

CYCLE = """
name: bad
steps:
  - name: a
    action: system_info
    depends_on: [b]
  - name: b
    action: disk_health
    depends_on: [a]
"""


def test_parse_and_validate_ok():
    rb = parse_runbook(VALID)
    assert rb.name == "demo"
    assert rb.max_concurrent == 2
    assert validate(rb) == []
    assert topo_order(rb) == ["inventory", "disk"]


def test_cycle_rejected():
    rb = parse_runbook(CYCLE)
    errors = validate(rb)
    assert any("cycle" in e for e in errors)
    with pytest.raises(ValueError):
        topo_order(rb)


def test_unknown_dependency_rejected():
    spec = "name: x\nsteps:\n  - {name: a, action: system_info, depends_on: [zzz]}\n"
    rb = parse_runbook(spec)
    assert any("unknown" in e for e in validate(rb))
