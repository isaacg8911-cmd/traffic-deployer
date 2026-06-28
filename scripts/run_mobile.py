"""Launch the Traffic Deployer mobile web server.

Binds 0.0.0.0 so a phone on the same network can reach it. Prints the LAN URL.

Phone browser geolocation needs a *secure context*, so by default this serves
HTTPS with a self-signed cert that names this PC's LAN IP. The phone accepts the
cert once ("not private" -> proceed), then "Grab GPS" works in the field.

Env overrides:
  TD_MOBILE_HTTP=1   force plain HTTP (drop-pin only; phone GPS will not work)
  TD_MOBILE_HOST     bind host (default 0.0.0.0)
  TD_MOBILE_PORT     port (default 8800)
"""
from __future__ import annotations

import os
import socket
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _resolve_tls(ip: str) -> tuple[str, str] | None:
    """Return (cert, key) for HTTPS, or None to serve plain HTTP."""
    if os.environ.get("TD_MOBILE_HTTP") == "1":
        return None
    from mobile_web import tls

    if not tls.tls_available():
        print("  [warn] `cryptography` not installed — serving plain HTTP.")
        print("         Phone GPS needs HTTPS; install with:")
        print("           pip install -r mobile_web\\requirements.txt")
        return None
    try:
        return tls.ensure_cert(ROOT, ip)
    except Exception as exc:  # pragma: no cover - defensive fallback
        print(f"  [warn] could not create TLS cert ({exc}); serving plain HTTP.")
        return None


def main() -> int:
    import uvicorn

    host = os.environ.get("TD_MOBILE_HOST", "0.0.0.0")
    port = int(os.environ.get("TD_MOBILE_PORT", "8800"))
    ip = lan_ip()
    tls_pair = _resolve_tls(ip)
    scheme = "https" if tls_pair else "http"

    print("=" * 60)
    print(" Traffic Deployer — MOBILE web server")
    print("=" * 60)
    print(f"  On this PC : {scheme}://127.0.0.1:{port}")
    print(f"  On phone   : {scheme}://{ip}:{port}   (same Wi-Fi)")
    if tls_pair:
        print("  Note       : phone shows a security warning the first time —")
        print("               tap Advanced -> proceed. Then 'Grab GPS' works.")
    else:
        print("  Note       : plain HTTP — phone GPS is blocked; drop-pin only.")
    print("  Stop       : Ctrl+C")
    print("=" * 60)

    kwargs: dict = {"host": host, "port": port, "log_level": "info"}
    if tls_pair:
        kwargs["ssl_certfile"], kwargs["ssl_keyfile"] = tls_pair
    uvicorn.run("mobile_web.server:app", **kwargs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
