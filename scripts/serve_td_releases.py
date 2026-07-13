"""Serve C:\\TDReleases on every non-loopback IPv4 (LAN + Tailscale)."""
from __future__ import annotations

import os
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def list_ips() -> list[str]:
    env = os.environ.get("TD_RELEASES_HOST", "").strip()
    if env:
        return [env]
    ips: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127.") or ip.startswith("169.254."):
                continue
            if ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    # Prefer known interfaces via UDP trick + common ranges
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127.") and ip not in ips:
            ips.insert(0, ip)
    except OSError:
        pass
    if not ips:
        ips = ["192.168.1.30"]
    return ips


def serve_one(host: str, port: int, root: str) -> None:
    os.chdir(root)

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            print(f"[{host}:{port}] {self.address_string()} - {fmt % args}", flush=True)

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving {root} at http://{host}:{port}/", flush=True)
    httpd.serve_forever()


def main() -> int:
    root = os.environ.get("TD_RELEASES_DIR", r"C:\TDReleases").strip() or r"C:\TDReleases"
    port = int(os.environ.get("TD_RELEASES_PORT", "8765") or "8765")
    if not os.path.isfile(os.path.join(root, "version.json")):
        print(f"FAIL: {root}\\version.json missing — run PUBLISH_APP_UPDATE.bat first.")
        return 1
    ips = list_ips()
    print("Traffic Deployer update server")
    print(f"  Folder: {root}")
    threads: list[threading.Thread] = []
    for ip in ips:
        t = threading.Thread(target=serve_one, args=(ip, port, root), daemon=True)
        t.start()
        threads.append(t)
        print(f"  URL   : http://{ip}:{port}/")
    print("  Leave this window open while the work laptop updates.")
    for t in threads:
        t.join()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
