"""
Crash-safe, optionally-encrypted local state persistence for Traffic Deployer.

Design goals:
- Never lose a shift: atomic writes (temp file + os.replace) so a file is never
  half-written, plus a single .bak of the last good state for belt-and-suspenders.
- Private by default: state is encrypted at rest with a local key (Fernet) so the
  weekly field data is not readable as plain text on disk.
- Self-contained & testable: pure functions, no Streamlit imports. Degrades to
  plaintext if `cryptography` is unavailable so data is never blocked.

Encrypted files are prefixed with MAGIC; the loader transparently reads both
encrypted and legacy plaintext files.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except Exception:
    HAS_CRYPTO = False

MAGIC = b"TDSENC1:"


def _key_path(data_dir: str) -> str:
    return os.path.join(data_dir, ".tds_key")


def _atomic_write_bytes(path: str, data: bytes) -> None:
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def _get_key(data_dir: str) -> bytes | None:
    if not HAS_CRYPTO:
        return None
    kp = _key_path(data_dir)
    try:
        if os.path.exists(kp):
            with open(kp, "rb") as f:
                return f.read().strip()
        key = Fernet.generate_key()
        _atomic_write_bytes(kp, key)
        try:
            os.chmod(kp, 0o600)
        except Exception:
            pass
        return key
    except Exception:
        return None


def _serialize(payload: dict, data_dir: str) -> bytes:
    raw = json.dumps(payload, default=str).encode("utf-8")
    key = _get_key(data_dir)
    if key and HAS_CRYPTO:
        try:
            return MAGIC + Fernet(key).encrypt(raw)
        except Exception:
            return raw
    return raw


def _deserialize(blob: bytes, data_dir: str) -> dict:
    if blob[: len(MAGIC)] == MAGIC and HAS_CRYPTO:
        key = _get_key(data_dir)
        if not key:
            raise ValueError("encrypted state but no key available")
        raw = Fernet(key).decrypt(blob[len(MAGIC):])
        return json.loads(raw.decode("utf-8"))
    return json.loads(blob.decode("utf-8"))


def save_state(payload: dict, path: str, data_dir: str) -> bool:
    """Atomically persist state (encrypted if possible), keeping one .bak."""
    try:
        blob = _serialize(payload, data_dir)
        if os.path.exists(path):
            try:
                shutil.copy2(path, path + ".bak")
            except Exception:
                pass
        _atomic_write_bytes(path, blob)
        return True
    except Exception:
        return False


def load_state(path: str, data_dir: str) -> dict:
    """Load state, transparently handling encrypted/plaintext and falling back to .bak."""
    for candidate in (path, path + ".bak"):
        try:
            if os.path.exists(candidate):
                with open(candidate, "rb") as f:
                    blob = f.read()
                if blob.strip():
                    return _deserialize(blob, data_dir)
        except Exception:
            continue
    return {}


if __name__ == "__main__":
    # Self-test round-trip (run: python persistence.py)
    import tempfile as _tf

    d = _tf.mkdtemp()
    p = os.path.join(d, "tds_backup_TEST.json")
    sample = {"driver": "TEST", "route": [1, 2, 3], "coords": (33.77, -117.94)}
    assert save_state(sample, p, d), "save failed"
    back = load_state(p, d)
    assert back["driver"] == "TEST" and back["route"] == [1, 2, 3], "round-trip mismatch"
    with open(p, "rb") as fh:
        head = fh.read(8)
    print("crypto available:", HAS_CRYPTO)
    print("encrypted on disk:", head == MAGIC)
    print("round-trip OK:", back)
