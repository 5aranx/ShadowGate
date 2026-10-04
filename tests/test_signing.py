
from shadowgate.crypto.signing import (
    generate_org_key,
    sign_manifest,
    verify_manifest,
)


def test_signing_roundtrip():
    key = generate_org_key()
    payload = {"name": "disk_health", "version": "1.0.0"}
    sig = sign_manifest(payload, key)
    assert verify_manifest(payload, sig, key) is True
    tampered = dict(payload, version="2.0.0")
    assert verify_manifest(tampered, sig, key) is False
