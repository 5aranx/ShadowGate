"""Runbook parsing, validation, and targeting.

A runbook is YAML:
  name: apt-upgrade
  max_concurrent: 2
  steps:
    - name: inventory
      action: system_info
      targets: {tag: linux}
      depends_on: []
    - name: disk
      action: disk_health
      targets: {tag: linux}
      depends_on: [inventory]
    - name: compensate-disk
      action: disk_health
      targets: {tag: linux}
      compensate_for: disk
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class Step:
    name: str
    action: str
    targets: dict[str, str] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    compensate_for: str | None = None


@dataclass
class Runbook:
    name: str
    max_concurrent: int = 4
    steps: list[Step] = field(default_factory=list)

    def step(self, name: str) -> Step | None:
        for s in self.steps:
            if s.name == name:
                return s
        return None


def parse_runbook(text: str) -> Runbook:
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict) or "steps" not in raw:
        raise ValueError("runbook must be a mapping with a 'steps' list")
    steps: list[Step] = []
    for s in raw["steps"]:
        steps.append(
            Step(
                name=str(s["name"]),
                action=str(s["action"]),
                targets=dict(s.get("targets", {})),
                depends_on=[str(d) for d in s.get("depends_on", [])],
                params=dict(s.get("params", {})),
                compensate_for=s.get("compensate_for"),
            )
        )
    return Runbook(
        name=str(raw.get("name", "unnamed")),
        max_concurrent=int(raw.get("max_concurrent", 4)),
        steps=steps,
    )


def validate(runbook: Runbook) -> list[str]:
    errors: list[str] = []
    names = [s.name for s in runbook.steps]
    if len(names) != len(set(names)):
        errors.append("duplicate step names")
    if runbook.max_concurrent < 1:
        errors.append("max_concurrent must be >= 1")
    nameset = set(names)
    for s in runbook.steps:
        for dep in s.depends_on:
            if dep not in nameset:
                errors.append(f"step '{s.name}' depends on unknown '{dep}'")
        if s.compensate_for is not None and s.compensate_for not in nameset:
            errors.append(f"step '{s.name}' compensates unknown '{s.compensate_for}'")
    # cycle detection via Kahn's algorithm
    indegree = {s.name: len(s.depends_on) for s in runbook.steps}
    dependents: dict[str, list[str]] = {s.name: [] for s in runbook.steps}
    for s in runbook.steps:
        for dep in s.depends_on:
            if dep in dependents:
                dependents[dep].append(s.name)
    ready = [n for n, d in indegree.items() if d == 0]
    visited = 0
    while ready:
        n = ready.pop()
        visited += 1
        for m in dependents.get(n, []):
            indegree[m] -= 1
            if indegree[m] == 0:
                ready.append(m)
    if visited != len(runbook.steps):
        errors.append("runbook contains a cycle")
    return errors


def topo_order(runbook: Runbook) -> list[str]:
    done: set[str] = set()
    order: list[str] = []
    remaining = {s.name: list(s.depends_on) for s in runbook.steps}
    while remaining:
        ready = sorted(n for n, deps in remaining.items() if all(d in done for d in deps))
        if not ready:
            raise ValueError("cycle in runbook")
        for n in ready:
            order.append(n)
            done.add(n)
            del remaining[n]
    return order


def matches(step: Step, agent_tags: str) -> bool:
    have = {t.strip() for t in agent_tags.split(",") if t.strip()}
    for key, want in step.targets.items():
        if key != "tag":
            continue
        wants = {w.strip() for w in want.split("|")}
        if not (have & wants):
            return False
    return True
