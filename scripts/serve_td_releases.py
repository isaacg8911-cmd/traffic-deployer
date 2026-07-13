"""Serve C:\\TDReleases on the LAN IP (coexists with MindLink on 127.0.0.1:8765)."""
from __future__ import annotations

import os
import socket
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def lan_ip() -> str:
    env = os.environ.get("TD_RELEASES_HOST", "").strip()
    if env:
        return env
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return "192.168.1.30"


def main() -> int:
    root = os.environ.get("TD_RELEASES_DIR", r"C:\TDReleases").strip() or r"C:\TDReleases"
    port = int(os.environ.get("TD_RELEASES_PORT", "8765") or "8765")
    host = lan_ip()
    if not os.path.isfile(os.path.join(root, "version.json")):
        print(f"FAIL: {root}\\version.json missing — run PUBLISH_APP_UPDATE.bat first.")
        return 1
    os.chdir(root)
    httpd = ThreadingHTTPServer((host, port), SimpleHTTPRequestHandler)
    print(f"Traffic Deployer update server")
    print(f"  Folder: {root}")
    print(f"  Setup : http://{host}:{port}/")
    print(f"  Leave this window open while the work laptop updates.")
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
