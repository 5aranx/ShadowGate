from __future__ import annotations

from pathlib import Path
from typing import Any

from shadowgate.plugins.base import ActionContext, ActionResult


class FileFetch:
    name = "file_fetch"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string"}, "max_bytes": {"type": "integer"}},
            "required": ["path"],
        }

    def run(self, ctx: ActionContext) -> ActionResult:
        path = Path(ctx.params["path"])
        if not path.is_file():
            return ActionResult(ok=False, error="not a file")
        limit = int(ctx.params.get("max_bytes", 4096))
        data = path.read_bytes()[:limit]
        return ActionResult(
            ok=True,
            data={"bytes": len(data), "truncated": path.stat().st_size > limit},
        )


action = FileFetch()
