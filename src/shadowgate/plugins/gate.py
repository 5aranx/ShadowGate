"""Signature gate for externally-installed plugins.

External plugin distributions ship a `shadowgate_plugin.json` manifest next to
their METADATA; it must verify against the pinned org public key before any of
their actions are loaded. Builtins ship in the package and are trusted.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib.metadata import Distribution, EntryPoint
from pathlib import Path
from typing import Any, cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from shadowgate.crypto.signing import verify_manifest

MANIFEST_FILE = "shadowgate_plugin.json"


def _org_public_key(pem: bytes) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem)
    assert isinstance(key, Ed25519PublicKey)
    return key


def _manifest_for(dist: Distribution) -> dict[str, Any] | None:
    dist_path = getattr(dist, "_path", None)
    if dist_path is None:
        return None
    path = Path(str(dist_path)) / MANIFEST_FILE
    if not path.is_file():
        return None
    try:
        manifest = cast(dict[str, Any], json.loads(path.read_text()))
    except json.JSONDecodeError:
        return None
    return manifest if isinstance(manifest, dict) else None


def make_verifier(org_public_pem: bytes) -> Callable[[EntryPoint], bool]:
    public = _org_public_key(org_public_pem)

    def allow(ep: EntryPoint) -> bool:
        dist = getattr(ep, "dist", None)
        if dist is None:
            return False
        manifest = _manifest_for(dist)
        if manifest is None:
            return False
        signature = manifest.pop("signature", None)
        if not isinstance(signature, str):
            return False
        return verify_manifest(manifest, signature, public)

    return allow
