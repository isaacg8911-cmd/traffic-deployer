"""Serve C:\\TDReleases on every non-loopback IPv4 (LAN + Tailscale)."""
from __future__ import annotations

import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from core.update_hosts import DEFAULT_PORT, list_bind_ips
except ImportError:
    DEFAULT_PORT = 8765

    def list_bind_ips() -> list[str]:
        import shutil
        import socket
        import subprocess

        env = os.environ.get("TD_RELEASES_HOST", "").strip()
        if env:
            return [env]
        ips: list[str] = []
        ts = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"
        if ts and os.path.isfile(ts):
            try:
                raw = subprocess.check_output(
                    [ts, "ip", "-4"], stderr=subprocess.DEVNULL, timeout=5
                )
                for line in raw.decode("ascii", "ignore").splitlines():
                    ip = line.strip()
                    if ip.count(".") == 3 and ip not in ips:
                        ips.append(ip)
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if ip.startswith("127.") or ip.startswith("169.254."):
                    continue
                if ip not in ips:
                    ips.append(ip)
        except OSError:
            pass
        return ips or ["192.168.1.30"]


def serve_one(host: str, port: int, root: str) -> None:
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            print(f"[{host}:{port}] {self.address_string()} - {fmt % args}", flush=True)

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving {root} at http://{host}:{port}/", flush=True)
    httpd.serve_forever()


def main() -> int:
    root = os.environ.get("TD_RELEASES_DIR", r"C:\TDReleases").strip() or r"C:\TDReleases"
    port = int(os.environ.get("TD_RELEASES_PORT", str(DEFAULT_PORT)) or DEFAULT_PORT)
    if not os.path.isdir(root):
        print(f"FAIL: {root} missing — run PUBLISH_APP_UPDATE.bat first.")
        return 1
    if not os.path.isfile(os.path.join(root, "version.json")):
        print(f"FAIL: {root}\\version.json missing — run PUBLISH_APP_UPDATE.bat first.")
        return 1
    os.chdir(root)
    ips = list_bind_ips()
    print("Traffic Deployer update server")
    print(f"  Folder: {root}")
    if not ips:
        print("FAIL: no LAN/Tailscale IPv4 to bind.")
        return 1
    threads: list[threading.Thread] = []
    for ip in ips:
        t = threading.Thread(target=serve_one, args=(ip, port, root), daemon=True)
        t.start()
        threads.append(t)
        print(f"  URL   : http://{ip}:{port}/")
    print("  Leave this window open while the work laptop updates.")
    print("  Laptop on Tailscale can use the 100.x URL even off home Wi-Fi.")
    for t in threads:
        t.join()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
