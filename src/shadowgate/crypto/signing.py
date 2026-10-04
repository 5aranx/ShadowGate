"""Plugin signing and verification using ed25519.

Org generates a keypair once; plugins signed with the private key are loaded
only if the embedded signature verifies against the pinned org public key.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


@dataclass(frozen=True)
class OrgKey:
    private: ed25519.Ed25519PrivateKey
    public: ed25519.Ed25519PublicKey

    def private_pem(self) -> bytes:
        return self.private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def public_pem(self) -> bytes:
        return self.public.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )


def generate_org_key() -> OrgKey:
    priv = ed25519.Ed25519PrivateKey.generate()
    return OrgKey(private=priv, public=priv.public_key())


def load_org_key(path: str | Path) -> OrgKey:
    data = Path(path).read_bytes()
    priv = serialization.load_pem_private_key(data, password=None)
    assert isinstance(priv, ed25519.Ed25519PrivateKey)
    return OrgKey(private=priv, public=priv.public_key())


def save_org_key(key: OrgKey, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(key.private_pem())
    p.chmod(0o600)


def sign_manifest(payload: dict[str, object], key: OrgKey) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = key.private.sign(canonical)
    return base64.b64encode(sig).decode()


def verify_manifest(payload: dict[str, object], signature_b64: str, key: OrgKey) -> bool:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    try:
        key.public.verify(base64.b64decode(signature_b64), canonical)
    except Exception:
        return False
    return True


def fingerprint(key: OrgKey) -> str:
    raw = key.public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()[:16]
