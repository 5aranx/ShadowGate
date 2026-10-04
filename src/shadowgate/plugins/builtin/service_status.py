from __future__ import annotations

import subprocess
from typing import Any

from shadowgate.plugins.base import ActionContext, ActionResult


class ServiceStatus:
    name = "service_status"

    def schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"unit": {"type": "string"}}, "required": ["unit"]}

    def run(self, ctx: ActionContext) -> ActionResult:
        unit = ctx.params["unit"]
        r = subprocess.run(
            ["systemctl", "is-active", unit], capture_output=True, text=True, timeout=10
        )
        return ActionResult(ok=True, data={"unit": unit, "active": r.stdout.strip()})


action = ServiceStatus()
