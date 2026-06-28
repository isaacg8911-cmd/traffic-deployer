"""Prove the mobile lane serves a real HTTPS secure context for phone GPS.

Phone geolocation only runs over HTTPS once the page is reached by LAN IP. This
boots the actual mobile server under uvicorn with the self-signed cert and:

  1. generates the cert and confirms the LAN IP + 127.0.0.1 are in the SAN
     (so the phone can reach it by IP without a name mismatch),
  2. starts uvicorn with ssl_certfile/ssl_keyfile in a background thread,
  3. makes a real TLS request to https://127.0.0.1:PORT/api/healthz and pins
     trust to our cert (verify=cert) — proving the handshake + secure context,
  4. confirms plain HTTP to the same port fails (it is HTTPS-only),
  5. confirms the HTTP opt-out path (TD_MOBILE_HTTP=1) resolves to no cert.

Writes logs/mobile_check/proofs/tls_prove.json. Exit 0 = all checks passed.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PROOF_DIR = os.path.join(ROOT, "logs", "mobile_check", "proofs")


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main() -> int:
    import httpx
    import uvicorn

    from mobile_web import tls

    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"[{'OK ' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    check("cryptography_available", tls.tls_available())
    if not tls.tls_available():
        return _finish(checks, 1)

    # 1. cert generation + SAN content
    lan = "192.168.7.50"  # representative LAN IP; SAN must include it + 127.0.0.1
    cert_path, key_path = tls.ensure_cert(ROOT, lan)
    check("cert_files_written", os.path.isfile(cert_path) and os.path.isfile(key_path))
    san = tls.cert_san_hosts(cert_path)
    check("san_has_lan_ip", lan in san, f"SAN={san}")
    check("san_has_loopback", "127.0.0.1" in san, f"SAN={san}")
    check("san_has_localhost", "localhost" in san, f"SAN={san}")

    # cert reuse is stable (same inputs -> no churn)
    cert2, _ = tls.ensure_cert(ROOT, lan)
    check("cert_reused_when_fresh", cert2 == cert_path)

    # 2. boot the real server over HTTPS with the cert
    port = _free_port()
    config = uvicorn.Config(
        "mobile_web.server:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        ssl_certfile=cert_path,
        ssl_keyfile=key_path,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    started = False
    for _ in range(100):
        if getattr(server, "started", False):
            started = True
            break
        time.sleep(0.1)
    check("https_server_started", started)

    try:
        if started:
            # 3. real TLS handshake, trust pinned to our self-signed cert
            url = f"https://127.0.0.1:{port}/api/healthz"
            r = httpx.get(url, verify=cert_path, timeout=10.0)
            check("https_healthz_200", r.status_code == 200, str(r.status_code))
            check("https_healthz_ok", r.json().get("ok") is True)

            # 4. plain HTTP to the HTTPS port must NOT succeed as HTTP
            http_failed = False
            try:
                httpx.get(f"http://127.0.0.1:{port}/api/healthz", timeout=5.0)
            except httpx.HTTPError:
                http_failed = True
            check("plain_http_rejected_on_tls_port", http_failed)
    finally:
        server.should_exit = True
        thread.join(timeout=10)

    # 5. HTTP opt-out path resolves to no cert (drop-pin-only mode)
    import importlib

    run_mobile = importlib.import_module("scripts.run_mobile")
    os.environ["TD_MOBILE_HTTP"] = "1"
    try:
        check("http_optout_returns_none", run_mobile._resolve_tls("10.0.0.5") is None)
    finally:
        os.environ.pop("TD_MOBILE_HTTP", None)

    failed = [c["name"] for c in checks if not c["ok"]]
    return _finish(checks, 0 if not failed else 1)


def _finish(checks: list[dict], code: int) -> int:
    os.makedirs(PROOF_DIR, exist_ok=True)
    report = {
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "passed": sum(1 for c in checks if c["ok"]),
        "total": len(checks),
        "failed": [c["name"] for c in checks if not c["ok"]],
        "checks": checks,
    }
    with open(os.path.join(PROOF_DIR, "tls_prove.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n{report['passed']}/{report['total']} checks passed.")
    if report["failed"]:
        print("FAILED:", ", ".join(report["failed"]))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
