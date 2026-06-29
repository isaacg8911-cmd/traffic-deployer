"""Prove the mobile public modes + share links.

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
  - REVOKE: admin can cut off a link (lost phone); the token then 404s; extend
    re-activates it
  - EXPIRY: a link past its expiry 404s even with a valid token; admin status
    reports "expired"; extend gives it more time

PUBLIC open-create checks (TD_MOBILE_PUBLIC=1 + TD_MOBILE_OPEN_CREATE=1):
  - config reports public_mode=true / can_create=true
  - demo/import creation is allowed without the admin key
  - separate jobs get separate tokens; one token cannot open the other job
  - revoke/status/extend still require the admin key

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

    for key in ("TD_MOBILE_PUBLIC", "TD_MOBILE_ADMIN_KEY", "TD_MOBILE_PUBLIC_URL", "TD_MOBILE_OPEN_CREATE"):
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

    # local revoke works on the trusted LAN without an admin key
    r = client.post("/api/jobs/demo")
    lbody = r.json()
    ljob, ltoken = lbody.get("job_id"), lbody.get("token")
    r = client.post(f"/api/jobs/{ljob}/revoke")
    check("local_revoke_ok", r.status_code == 200 and r.json().get("link_status") == "revoked")
    r = client.get(f"/api/jobs/{ljob}", headers={"x-job-token": ltoken})
    check("local_revoked_token_blocked", r.status_code == 404, str(r.status_code))

    # ----------------------------------------------------------------- PUBLIC
    public_origin = "https://demo-test.trycloudflare.com"
    pclient, server_pub = _fresh_client(
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

    # ------------------------------------------------- REVOKE (lost phone)
    admin_h = {"x-admin-key": "secret-admin"}
    # link management needs the job's own token or the admin key (no anonymous management)
    r = pclient.post(f"/api/jobs/{pjob}/revoke")
    check("revoke_requires_auth", r.status_code == 404, str(r.status_code))
    # admin revokes the link (fallback for a lost phone, without the token)
    r = pclient.post(f"/api/jobs/{pjob}/revoke", headers=admin_h)
    check("revoke_with_admin_ok", r.status_code == 200 and r.json().get("link_status") == "revoked")
    # the valid token no longer opens the job
    r = pclient.get(f"/api/jobs/{pjob}", headers={"x-job-token": ptoken})
    check("revoked_token_blocked", r.status_code == 404, str(r.status_code))
    # admin status reports revoked without needing the token
    r = pclient.get(f"/api/jobs/{pjob}/status", headers=admin_h)
    check("admin_status_revoked", r.status_code == 200 and r.json().get("link_status") == "revoked")
    # extend re-activates (un-revokes) the link
    r = pclient.post(f"/api/jobs/{pjob}/extend", headers=admin_h, json={"hours": 4})
    check("extend_reactivates", r.status_code == 200 and r.json().get("link_status") == "active")
    r = pclient.get(f"/api/jobs/{pjob}", headers={"x-job-token": ptoken})
    check("reactivated_token_works", r.status_code == 200, str(r.status_code))

    # ------------------------------------------------- EXPIRY (self-timeout)
    r = pclient.post("/api/jobs/demo", headers=admin_h)
    ebody = r.json()
    ejob, etoken = ebody.get("job_id"), ebody.get("token")
    r = pclient.get(f"/api/jobs/{ejob}", headers={"x-job-token": etoken})
    check("expiry_job_open_before", r.status_code == 200, str(r.status_code))
    # force the link past its expiry (simulate the shift ending)
    job_obj = server_pub.store.load(ejob)
    job_obj["expires_at"] = time.time() - 5
    server_pub.store.save(job_obj)
    r = pclient.get(f"/api/jobs/{ejob}", headers={"x-job-token": etoken})
    check("expired_token_blocked", r.status_code == 404, str(r.status_code))
    r = pclient.get(f"/api/jobs/{ejob}/status", headers=admin_h)
    check("admin_status_expired", r.status_code == 200 and r.json().get("link_status") == "expired")
    # extend gives it more time and re-opens it
    r = pclient.post(f"/api/jobs/{ejob}/extend", headers=admin_h, json={"hours": 2})
    check("extend_after_expiry", r.status_code == 200 and r.json().get("link_status") == "active")
    r = pclient.get(f"/api/jobs/{ejob}", headers={"x-job-token": etoken})
    check("extended_token_works", r.status_code == 200, str(r.status_code))

    # ------------------------------------------------- PUBLIC OPEN-CREATE
    oclient, _ = _fresh_client(
        {
            "TD_MOBILE_PUBLIC": "1",
            "TD_MOBILE_OPEN_CREATE": "1",
            "TD_MOBILE_ADMIN_KEY": "secret-admin",
            "TD_MOBILE_PUBLIC_URL": public_origin,
        }
    )
    r = oclient.get("/api/config")
    ocfg = r.json()
    check("open_public_config_is_public", ocfg.get("public_mode") is True)
    check("open_public_can_create", ocfg.get("can_create") is True)

    r = oclient.post("/api/jobs/demo")
    check("open_demo_no_key", r.status_code == 200, str(r.status_code))
    obody1 = r.json()
    ojob1, otoken1 = obody1.get("job_id"), obody1.get("token")
    r = oclient.post("/api/jobs/demo")
    check("open_second_job_no_key", r.status_code == 200, str(r.status_code))
    obody2 = r.json()
    ojob2, otoken2 = obody2.get("job_id"), obody2.get("token")
    check("open_jobs_have_separate_ids", bool(ojob1 and ojob2 and ojob1 != ojob2))
    check("open_jobs_have_separate_tokens", bool(otoken1 and otoken2 and otoken1 != otoken2))

    r = oclient.get(f"/api/jobs/{ojob1}", headers={"x-job-token": otoken1})
    check("open_job1_token_opens_job1", r.status_code == 200, str(r.status_code))
    r = oclient.get(f"/api/jobs/{ojob1}", headers={"x-job-token": otoken2})
    check("open_job2_token_cannot_open_job1", r.status_code == 404, str(r.status_code))

    r = oclient.post("/api/jobs/import", data={})
    check("open_import_no_key_reaches_validation", r.status_code == 422, str(r.status_code))

    # Equal use: each coworker self-manages their OWN job with its link token.
    j1 = {"x-job-token": otoken1}
    r = oclient.get(f"/api/jobs/{ojob1}/status", headers=j1)
    check("self_status_with_own_token", r.status_code == 200 and r.json().get("link_status") == "active")
    r = oclient.post(f"/api/jobs/{ojob1}/extend", headers=j1, json={"hours": 4})
    check("self_extend_with_own_token", r.status_code == 200 and r.json().get("link_status") == "active")
    r = oclient.post(f"/api/jobs/{ojob1}/revoke", headers=j1)
    check("self_revoke_with_own_token", r.status_code == 200 and r.json().get("link_status") == "revoked")
    r = oclient.get(f"/api/jobs/{ojob1}", headers=j1)
    check("self_revoked_token_blocked", r.status_code == 404, str(r.status_code))
    r = oclient.post(f"/api/jobs/{ojob1}/extend", headers=j1, json={"hours": 4})
    check("self_unrevoke_with_own_token", r.status_code == 200 and r.json().get("link_status") == "active")
    r = oclient.get(f"/api/jobs/{ojob1}", headers=j1)
    check("self_reopened_after_extend", r.status_code == 200, str(r.status_code))

    # A coworker cannot manage someone else's job with their own (different) token.
    r = oclient.post(f"/api/jobs/{ojob1}/revoke", headers={"x-job-token": otoken2})
    check("cross_job_manage_blocked", r.status_code == 404, str(r.status_code))
    # No anonymous management.
    r = oclient.post(f"/api/jobs/{ojob1}/revoke")
    check("anon_manage_blocked", r.status_code == 404, str(r.status_code))
    # Admin key still works as a fallback.
    r = oclient.post(f"/api/jobs/{ojob1}/revoke", headers=admin_h)
    check("admin_fallback_revoke_ok", r.status_code == 200 and r.json().get("link_status") == "revoked")

    # reset env so we don't leak public mode to other in-process steps
    for key in ("TD_MOBILE_PUBLIC", "TD_MOBILE_ADMIN_KEY", "TD_MOBILE_PUBLIC_URL", "TD_MOBILE_OPEN_CREATE"):
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
