"""Prove the mobile share-only PUBLIC mode + share links.

Covers the public field model: "text a link, phone works anywhere", but the
public start page cannot create or browse jobs.

LOCAL mode checks (default env):
  - config reports public_mode=false / can_create=true
  - demo job can be created without an admin key
  - the create response carries an absolute share_url -> /join/<id>?token=...
  - /api/jobs/{id}/share returns the same link (token required)
  - QR SVG renders for the share link
  - /join/<id> serves the PWA shell (so the link opens the app)

PUBLIC mode checks (TD_MOBILE_PUBLIC=1, fresh app import):
  - config reports public_mode=true / can_create=false
  - demo + import creation are BLOCKED without the admin key (403)
  - creation WORKS with the admin key, and the share_url uses TD_MOBILE_PUBLIC_URL
  - a crew member can open the job from the share link's job_id + token
  - a wrong token on the share link is rejected

Writes logs/mobile_check/proofs/share_prove.json. Exit 0 = all checks passed.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PROOF_DIR = os.path.join(ROOT, "logs", "mobile_check", "proofs")


def _fresh_client(env: dict):
    """Build a TestClient against a freshly-imported server module so module-level
    settings (public mode) are evaluated under the given environment."""
    from fastapi.testclient import TestClient

    for key in ("TD_MOBILE_PUBLIC", "TD_MOBILE_ADMIN_KEY", "TD_MOBILE_PUBLIC_URL"):
        os.environ.pop(key, None)
    os.environ.update(env)

    import mobile_web.settings as settings_mod
    import mobile_web.server as server_mod

    importlib.reload(settings_mod)
    server_mod = importlib.reload(server_mod)
    return TestClient(server_mod.app), server_mod


def main() -> int:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"[{'OK ' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    # ----------------------------------------------------------------- LOCAL
    client, _ = _fresh_client({})
    r = client.get("/api/config")
    cfg = r.json()
    check("local_config_not_public", r.status_code == 200 and cfg.get("public_mode") is False)
    check("local_can_create", cfg.get("can_create") is True)

    r = client.post("/api/jobs/demo")
    check("local_demo_no_key", r.status_code == 200, str(r.status_code))
    body = r.json()
    job_id, token = body.get("job_id"), body.get("token")
    share_url = body.get("share_url", "")
    check("share_url_present", bool(share_url), share_url)
    check("share_url_has_join_path", f"/join/{job_id}" in share_url, share_url)
    check("share_url_has_token", "token=" in share_url)

    r = client.get(f"/api/jobs/{job_id}/share", headers={"x-job-token": token})
    check("share_endpoint_ok", r.status_code == 200 and f"/join/{job_id}" in r.json().get("share_url", ""))
    r = client.get(f"/api/jobs/{job_id}/share")  # no token
    check("share_endpoint_requires_token", r.status_code == 404, str(r.status_code))

    r = client.get(f"/api/jobs/{job_id}/share.svg", headers={"x-job-token": token})
    svg_ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("image/svg")
    check("share_qr_svg", svg_ok, str(r.status_code))

    r = client.get(f"/join/{job_id}")
    check("join_serves_pwa_shell", r.status_code == 200 and "Traffic Deployer" in r.text)

    # ----------------------------------------------------------------- PUBLIC
    public_origin = "https://demo-test.trycloudflare.com"
    pclient, _ = _fresh_client(
        {"TD_MOBILE_PUBLIC": "1", "TD_MOBILE_ADMIN_KEY": "secret-admin", "TD_MOBILE_PUBLIC_URL": public_origin}
    )

    r = pclient.get("/api/config")
    pcfg = r.json()
    check("public_config_is_public", pcfg.get("public_mode") is True)
    check("public_cannot_create_flag", pcfg.get("can_create") is False)

    # creation blocked without admin key
    r = pclient.post("/api/jobs/demo")
    check("public_demo_blocked_no_key", r.status_code == 403, str(r.status_code))
    r = pclient.post("/api/jobs/import", data={"home_lat": "33.8", "home_lon": "-117.9"})
    check("public_import_blocked_no_key", r.status_code == 403, str(r.status_code))

    # creation works with admin key
    r = pclient.post("/api/jobs/demo", headers={"x-admin-key": "secret-admin"})
    check("public_demo_with_key", r.status_code == 200, str(r.status_code))
    pbody = r.json()
    pjob, ptoken = pbody.get("job_id"), pbody.get("token")
    pshare = pbody.get("share_url", "")
    check("public_share_uses_public_url", pshare.startswith(public_origin + f"/join/{pjob}"), pshare)

    # wrong admin key rejected
    r = pclient.post("/api/jobs/demo", headers={"x-admin-key": "nope"})
    check("public_wrong_admin_key_rejected", r.status_code == 403, str(r.status_code))

    # crew opens the job from the share link (job_id + token), no admin key
    r = pclient.get(f"/api/jobs/{pjob}", headers={"x-job-token": ptoken})
    check("crew_open_from_share_link", r.status_code == 200, str(r.status_code))
    # wrong token on the share link is rejected
    r = pclient.get(f"/api/jobs/{pjob}", headers={"x-job-token": "wrong"})
    check("share_wrong_token_rejected", r.status_code == 404, str(r.status_code))

    # reset env so we don't leak public mode to other in-process steps
    for key in ("TD_MOBILE_PUBLIC", "TD_MOBILE_ADMIN_KEY", "TD_MOBILE_PUBLIC_URL"):
        os.environ.pop(key, None)

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
    with open(os.path.join(PROOF_DIR, "share_prove.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n{report['passed']}/{report['total']} checks passed.")
    if report["failed"]:
        print("FAILED:", ", ".join(report["failed"]))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
