"""Smoke a deployed (or containerized) mobile host over real HTTP.

Verifies the always-on deploy behaves like the proven in-process server:
  - /api/healthz is up
  - public/share-only mode is on (start page can't create jobs)
  - job creation is blocked without the admin key (403), works with it
  - the create response carries an absolute https share_url
  - a crew member can open the job from job_id + token
  - admin can revoke the link; the token then 404s; extend re-activates it

Use it against a local container OR your live Render/Fly URL:
  python scripts/mobile_host_smoke.py --url http://127.0.0.1:8099 --admin-key secret-admin
  python scripts/mobile_host_smoke.py --url https://td.onrender.com --admin-key <key>

Exit 0 = all checks passed.
"""
from __future__ import annotations

import argparse
import os
import sys
import time


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Smoke a deployed mobile host.")
    p.add_argument("--url", default=os.environ.get("TD_MOBILE_PUBLIC_URL", "http://127.0.0.1:8099"))
    p.add_argument("--admin-key", default=os.environ.get("TD_MOBILE_ADMIN_KEY", "secret-admin"))
    p.add_argument("--wait", type=float, default=30.0, help="seconds to wait for healthz")
    args = p.parse_args(argv)

    try:
        import httpx
    except ImportError:
        print("httpx required: pip install httpx", file=sys.stderr)
        return 2

    base = args.url.rstrip("/")
    admin_h = {"x-admin-key": args.admin_key}
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))
        print(f"[{'OK ' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))

    # wait for the server to answer healthz (container/cold start)
    healthy = False
    deadline = time.time() + args.wait
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base}/api/healthz", timeout=5.0)
            if r.status_code == 200 and r.json().get("ok"):
                healthy = True
                break
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    check("healthz_up", healthy)
    if not healthy:
        return _finish(checks)

    r = httpx.get(f"{base}/api/config", timeout=10.0)
    cfg = r.json()
    check("public_mode_on", cfg.get("public_mode") is True and cfg.get("can_create") is False, str(cfg))

    r = httpx.post(f"{base}/api/jobs/demo", timeout=180.0)
    check("create_blocked_no_key", r.status_code == 403, str(r.status_code))

    # Simulate the platform TLS edge (Render/Fly) so we can prove --proxy-headers
    # yields an https share link even when this smoke hits the box over http.
    edge_h = dict(admin_h)
    edge_h["x-forwarded-proto"] = "https"
    r = httpx.post(f"{base}/api/jobs/demo", headers=edge_h, timeout=180.0)
    check("create_with_key", r.status_code == 200, str(r.status_code))
    body = r.json() if r.status_code == 200 else {}
    job_id, token = body.get("job_id"), body.get("token")
    share = body.get("share_url", "")
    check("share_url_https", share.startswith("https://") and f"/join/{job_id}" in share, share)

    if job_id and token:
        token_h = {"x-job-token": token}
        r = httpx.get(f"{base}/api/jobs/{job_id}", headers=token_h, timeout=30.0)
        check("crew_open_from_link", r.status_code == 200, str(r.status_code))

        r = httpx.post(f"{base}/api/jobs/{job_id}/revoke", headers=admin_h, timeout=30.0)
        check("admin_revoke", r.status_code == 200 and r.json().get("link_status") == "revoked")

        r = httpx.get(f"{base}/api/jobs/{job_id}", headers=token_h, timeout=30.0)
        check("revoked_token_blocked", r.status_code == 404, str(r.status_code))

        r = httpx.post(f"{base}/api/jobs/{job_id}/extend", headers=admin_h, json={"hours": 4}, timeout=30.0)
        check("extend_reactivates", r.status_code == 200 and r.json().get("link_status") == "active")

        r = httpx.get(f"{base}/api/jobs/{job_id}", headers=token_h, timeout=30.0)
        check("reactivated_token_works", r.status_code == 200, str(r.status_code))

    return _finish(checks)


def _finish(checks: list[tuple[str, bool, str]]) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\n{passed}/{len(checks)} checks passed.")
    failed = [n for n, ok, _ in checks if not ok]
    if failed:
        print("FAILED:", ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
