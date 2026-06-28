"""Self-signed TLS for the mobile lane.

Phone browser geolocation only runs in a *secure context*. That means HTTPS once
the page is served over the LAN by IP (plain http://<ip> silently blocks
getCurrentPosition). For a self-contained field tool we generate a local
self-signed certificate that names this PC's LAN IP (plus localhost / 127.0.0.1)
in its Subject Alternative Names, so the phone can reach it directly.

The phone has to accept the certificate once ("not private" -> proceed). After
that, geolocation works. No external CA, no internet, no keys in the repo —
certs live under tds_data/mobile_certs/ (git-ignored field data).

Generation needs `cryptography`. If it is unavailable the launcher falls back to
plain HTTP (drop-pin still works; phone GPS does not).
"""
from __future__ import annotations

import datetime
import ipaddress
import os

CERT_DIRNAME = os.path.join("tds_data", "mobile_certs")
CERT_NAME = "mobile_lan.crt"
KEY_NAME = "mobile_lan.key"
# Bump if the cert contents/shape change so stale certs get regenerated.
META_NAME = "mobile_lan.meta"
META_VERSION = "1"


def tls_available() -> bool:
    try:
        import cryptography  # noqa: F401

        return True
    except ImportError:
        return False


def cert_dir(root: str) -> str:
    return os.path.join(root, CERT_DIRNAME)


def cert_paths(root: str) -> tuple[str, str]:
    d = cert_dir(root)
    return os.path.join(d, CERT_NAME), os.path.join(d, KEY_NAME)


def _meta_path(root: str) -> str:
    return os.path.join(cert_dir(root), META_NAME)


def _meta_signature(hosts: list[str]) -> str:
    return META_VERSION + "|" + ",".join(sorted(hosts))


def _is_fresh(root: str, hosts: list[str]) -> bool:
    cert, key = cert_paths(root)
    meta = _meta_path(root)
    if not (os.path.isfile(cert) and os.path.isfile(key) and os.path.isfile(meta)):
        return False
    try:
        with open(meta, encoding="utf-8") as f:
            if f.read().strip() != _meta_signature(hosts):
                return False
    except OSError:
        return False
    # Regenerate well before expiry so a long-lived dev box never serves a dead cert.
    try:
        from cryptography import x509

        with open(cert, "rb") as f:
            crt = x509.load_pem_x509_certificate(f.read())
        not_after = getattr(crt, "not_valid_after_utc", None) or crt.not_valid_after
        now = datetime.datetime.now(datetime.timezone.utc)
        if not_after.tzinfo is None:
            now = now.replace(tzinfo=None)
        return (not_after - now).days > 14
    except Exception:
        return False


def ensure_cert(root: str, lan_ip: str | None = None) -> tuple[str, str]:
    """Return (cert_path, key_path), generating a self-signed cert if needed.

    Raises RuntimeError if `cryptography` is not installed.
    """
    if not tls_available():
        raise RuntimeError("cryptography not installed; cannot create TLS cert")

    hostnames = ["localhost"]
    ip_addresses = ["127.0.0.1"]
    if lan_ip and lan_ip not in ("127.0.0.1", "0.0.0.0"):
        ip_addresses.append(lan_ip)

    signature_hosts = hostnames + ip_addresses
    cert_path, key_path = cert_paths(root)
    if _is_fresh(root, signature_hosts):
        return cert_path, key_path

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    os.makedirs(cert_dir(root), exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Traffic Deployer Mobile"),
            x509.NameAttribute(NameOID.COMMON_NAME, lan_ip or "localhost"),
        ]
    )
    san = [x509.DNSName(h) for h in hostnames] + [
        x509.IPAddress(ipaddress.ip_address(ip)) for ip in ip_addresses
    ]
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    with open(key_path, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(_meta_path(root), "w", encoding="utf-8") as f:
        f.write(_meta_signature(signature_hosts))

    return cert_path, key_path


def cert_san_hosts(cert_path: str) -> list[str]:
    """Read SAN entries (DNS + IP) from a PEM cert — used by the proof script."""
    from cryptography import x509

    with open(cert_path, "rb") as f:
        crt = x509.load_pem_x509_certificate(f.read())
    ext = crt.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    out = list(ext.get_values_for_type(x509.DNSName))
    out += [str(ip) for ip in ext.get_values_for_type(x509.IPAddress)]
    return out
