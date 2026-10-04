from __future__ import annotations

import importlib.metadata
from typing import Any

from shadowgate.plugins.base import Registry

ENTRY_GROUP = "shadowgate.actions"


def load_builtins(registry: Registry) -> None:
    from shadowgate.plugins.builtin import disk_health, file_fetch, service_status, system_info

    for mod in (system_info, file_fetch, service_status, disk_health):
        registry.register(mod.action)


def load_entry_points(registry: Registry) -> list[str]:
    loaded: list[str] = []
    for ep in importlib.metadata.entry_points(group=ENTRY_GROUP):
        obj: Any = ep.load()
        action = obj() if isinstance(obj, type) else obj
        registry.register(action)
        loaded.append(action.name)
    return loaded
