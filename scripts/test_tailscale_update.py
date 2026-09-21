"""Prove Tailscale/LAN update channel fallbacks and download-host rewrite."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import update_check as uc
from core.update_check import rewrite_download_url
from core.update_hosts import FALLBACK_TAILSCALE_IP, list_base_urls


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def test_rewrite() -> None:
    got = rewrite_download_url(
        "http://100.93.14.32:8765/version.json",
        "http://192.168.1.30:8765/TrafficDeployer-AppUpdate.zip",
    )
    if got != "http://100.93.14.32:8765/TrafficDeployer-AppUpdate.zip":
        _fail(f"rewrite kept LAN host: {got}")
    empty = rewrite_download_url("http://msi.tailaf9051.ts.net:8765/version.json", "")
    if empty != "http://msi.tailaf9051.ts.net:8765/TrafficDeployer-AppUpdate.zip":
        _fail(f"rewrite empty download: {empty}")


def test_bases_include_tailscale_fallback() -> None:
    bases = list_base_urls(8765)
    blob = " ".join(bases)
    if FALLBACK_TAILSCALE_IP not in blob and "100." not in blob:
        _fail(f"no Tailscale URL in {bases}")
    if "8765" not in blob:
        _fail(f"port missing in {bases}")


def test_channel_urls_and_fallback(tmp: str) -> None:
    channel = os.path.join(tmp, "update_channel.json")
    home_txt = os.path.join(tmp, "wifi_update_home.txt")
    os.environ.pop("TD_UPDATE_URL", None)
    os.environ.pop("TD_UPDATE_HOME", None)
    uc.CHANNEL_FILE = channel
    uc.HOME_TXT = home_txt

    with open(home_txt, "w", encoding="ascii") as f:
        f.write("http://100.93.14.32:8765\nhttp://192.168.1.30:8765\n")
    urls = uc.channel_urls()
    if "http://100.93.14.32:8765/version.json" not in urls:
        _fail(f"home txt not read: {urls}")

    payload = {
        "version": "9.9.9",
        "download_url": "http://192.168.1.30:8765/TrafficDeployer-AppUpdate.zip",
        "sha256": "abc",
        "notes": "test",
    }
    body = json.dumps(payload).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/version.json":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    good = f"http://127.0.0.1:{port}/version.json"
    with open(channel, "w", encoding="utf-8") as f:
        json.dump(
            {
                "version_url": good,
                "version_urls": [
                    "http://127.0.0.1:1/version.json",
                    good,
                ],
            },
            f,
        )
    try:
        info = uc.check_for_update("1.0.0")
        if info.error:
            _fail(f"fallback should succeed, got error: {info.error}")
        if info.latest != "9.9.9" or not info.update_available:
            _fail(f"unexpected info: {info}")
        if info.download_url != f"http://127.0.0.1:{port}/TrafficDeployer-AppUpdate.zip":
            _fail(f"download not rewritten to reachable host: {info.download_url}")
        uc.CHANNEL_FILE = os.path.join(tmp, "missing.json")
        uc.HOME_TXT = os.path.join(tmp, "missing.txt")
        os.environ.pop("TD_UPDATE_URL", None)
        none = uc.check_for_update("1.0.0")
        if "No update channel" not in none.error:
            _fail(f"expected missing-channel error, got {none.error!r}")
        uc.CHANNEL_FILE = channel
        with open(channel, "w", encoding="utf-8") as f:
            json.dump({"version_urls": ["http://127.0.0.1:1/version.json"]}, f)
        uc.HOME_TXT = os.path.join(tmp, "missing.txt")
        unreachable = uc.check_for_update("1.0.0")
        if "Could not reach update server" not in unreachable.error:
            _fail(f"expected unreachable, got {unreachable.error!r}")
    finally:
        httpd.shutdown()


def main() -> int:
    print("TAILSCALE UPDATE — channel fallback + host rewrite")
    test_rewrite()
    print("  OK  download host rewrite (LAN URL -> Tailscale origin)")
    test_bases_include_tailscale_fallback()
    print("  OK  home bases include Tailscale")
    with tempfile.TemporaryDirectory() as tmp:
        test_channel_urls_and_fallback(tmp)
    print("  OK  first URL fails, second serves; missing channel errors")
    print("PASS: tailscale update channel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
