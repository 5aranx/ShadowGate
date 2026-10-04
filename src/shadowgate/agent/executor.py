from __future__ import annotations

from shadowgate.plugins.base import ActionContext, ActionResult, Registry


class Executor:
    def __init__(self, registry: Registry, agent_id: str) -> None:
        self.registry = registry
        self.agent_id = agent_id

    def run(self, job_id: str, action: str, params: dict[str, object]) -> ActionResult:
        try:
            act = self.registry.get(action)
        except KeyError:
            return ActionResult(ok=False, error=f"unknown action: {action}")
        ctx = ActionContext(agent_id=self.agent_id, job_id=job_id, params=params)
        try:
            return act.run(ctx)
        except Exception as exc:
            return ActionResult(ok=False, error=str(exc))
