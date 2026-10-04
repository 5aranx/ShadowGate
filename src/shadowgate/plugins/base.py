from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ActionContext:
    agent_id: str
    job_id: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@runtime_checkable
class Action(Protocol):
    name: str

    def schema(self) -> dict[str, Any]: ...
    def run(self, ctx: ActionContext) -> ActionResult: ...


class Registry:
    def __init__(self) -> None:
        self._actions: dict[str, Action] = {}

    def register(self, action: Action) -> None:
        if action.name in self._actions:
            raise ValueError(f"duplicate action: {action.name}")
        self._actions[action.name] = action

    def get(self, name: str) -> Action:
        if name not in self._actions:
            raise KeyError(f"unknown action: {name}")
        return self._actions[name]

    def names(self) -> list[str]:
        return sorted(self._actions)
