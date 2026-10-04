"""Append-only hash-chained audit log.

Each entry embeds the SHA-256 of the previous entry's canonical serialized
form. verify_chain walks the log and fails on any mutation, reorder, or
deletion.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def _canonical(entry: dict[str, Any]) -> bytes:
    return json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class AuditLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def _last_hash(self) -> str:
        last = GENESIS
        for line in self.path.read_text().splitlines():
            if line.strip():
                with contextlib.suppress(json.JSONDecodeError, KeyError):
                    last = json.loads(line)["hash"]
        return last

    def append(
        self, event: str, actor: str, target: str, detail: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        prev = self._last_hash()
        entry: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            "actor": actor,
            "target": target,
            "detail": detail or {},
            "prev": prev,
        }
        entry["hash"] = _digest(_canonical(entry))
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def entries(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for line in self.path.read_text().splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out

    def verify_chain(self) -> bool:
        prev = GENESIS
        for entry in self.entries():
            if entry.get("prev") != prev:
                return False
            expected = _digest(_canonical({k: v for k, v in entry.items() if k != "hash"}))
            if expected != entry.get("hash"):
                return False
            prev = entry["hash"]
        return True
