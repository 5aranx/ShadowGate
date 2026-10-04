from __future__ import annotations

import platform
from typing import Any

from shadowgate.plugins.base import ActionContext, ActionResult


class SystemInfo:
    name = "system_info"

    def schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    def run(self, ctx: ActionContext) -> ActionResult:
        return ActionResult(ok=True, data={
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "node": platform.node(),
        })


action = SystemInfo()
