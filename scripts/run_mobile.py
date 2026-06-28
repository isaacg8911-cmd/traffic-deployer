"""Launch the Traffic Deployer mobile web server.

Binds 0.0.0.0 so a phone on the same network can reach it. Prints the LAN URL.
Note: phone browser geolocation requires a secure context — works on localhost,
and over LAN needs HTTPS or Chrome's "treat insecure origin as secure" flag.
For production, put this behind an HTTPS reverse proxy / host.
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


def main() -> int:
    import uvicorn

    host = os.environ.get("TD_MOBILE_HOST", "0.0.0.0")
    port = int(os.environ.get("TD_MOBILE_PORT", "8800"))
    ip = lan_ip()
    print("=" * 60)
    print(" Traffic Deployer — MOBILE web server")
    print("=" * 60)
    print(f"  On this PC : http://127.0.0.1:{port}")
    print(f"  On phone   : http://{ip}:{port}   (same Wi-Fi)")
    print("  Stop       : Ctrl+C")
    print("=" * 60)
    uvicorn.run("mobile_web.server:app", host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
