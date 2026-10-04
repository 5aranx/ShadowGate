from __future__ import annotations

import shutil
from typing import Any

from shadowgate.plugins.base import ActionContext, ActionResult


class DiskHealth:
    name = "disk_health"

    def schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"path": {"type": "string"}}}

    def run(self, ctx: ActionContext) -> ActionResult:
        path = ctx.params.get("path", "/")
        usage = shutil.disk_usage(path)
        return ActionResult(ok=True, data={
            "path": path,
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": round(usage.used / usage.total * 100, 1),
        })


action = DiskHealth()
