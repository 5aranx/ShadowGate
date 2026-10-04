"""Mutual-TLS identity: a local CA issues a per-agent client certificate.

In production agents pin the server CA and the server pins agent certs.
For dev, --insecure-dev self-signs everything on first boot.
"""

from __future__ import annotations

import datetime as dt
from ipaddress import IPv4Address
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def _names(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _load_key(path: Path) -> rsa.RSAPrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
    return key


def _load_cert(path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(path.read_bytes())


def ensure_ca(key_path: str, cert_path: str, common_name: str = "shadowgate-ca") -> None:
    kp, cp = Path(key_path), Path(cert_path)
    if kp.exists() and cp.exists():
        return
    kp.parent.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(_names(common_name))
        .issuer_name(_names(common_name))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=False, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=False, decipher_only=False,
        ), critical=True)
        .sign(key, hashes.SHA256())
    )
    kp.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    kp.chmod(0o600)
    cp.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def issue_agent_cert(
    ca_key_path: str, ca_cert_path: str,
    agent_id: str, out_key: str, out_cert: str, days: int = 365,
) -> None:
    Path(out_key).parent.mkdir(parents=True, exist_ok=True)
    ca_key = _load_key(Path(ca_key_path))
    ca_cert = _load_cert(Path(ca_cert_path))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(_names(agent_id))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(hours=1))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(
            [x509.DNSName(agent_id), x509.IPAddress(IPv4Address("127.0.0.1"))]
        ), critical=False)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]), critical=True
        )
        .sign(ca_key, hashes.SHA256())
    )
    Path(out_key).write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    Path(out_key).chmod(0o600)
    Path(out_cert).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
