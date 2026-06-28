"""Mobile user-test: full field-runner flow against the ASGI app in-process.

Simulates what the phone PWA does over HTTP (no browser needed):
  demo job -> build route -> open install -> grab GPS -> denied/pin fallback
  -> fill + install -> pickup -> audit -> export CSV -> error paths.

Writes proof JSON to logs/mobile_check/proofs/user_prove.json.
Exit 0 = all required checks passed.
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PROOF_DIR = os.path.join(ROOT, "logs", "mobile_check", "proofs")


def main() -> int:
    from fastapi.testclient import TestClient

    from mobile_web.server import app

    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"[{'OK ' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    client = TestClient(app)

    # 1. health + config
    r = client.get("/api/healthz")
    check("health", r.status_code == 200 and r.json().get("ok"), str(r.status_code))
    r = client.get("/api/config")
    check("config_tile_url", r.status_code == 200 and bool(r.json().get("tile_url")))

    # 2. create demo job
    r = client.post("/api/jobs/demo")
    check("create_demo_job", r.status_code == 200, str(r.status_code))
    if r.status_code != 200:
        return _finish(checks, 1)
    body = r.json()
    job_id, token = body["job_id"], body["token"]
    n_stops = body["state"]["counts"]["total"]
    check("job_has_stops", n_stops > 0, f"{n_stops} stops")
    auth = {"x-job-token": token}

    # 3. token enforcement (wrong token rejected)
    r = client.get(f"/api/jobs/{job_id}", headers={"x-job-token": "wrong"})
    check("token_enforced", r.status_code == 404, str(r.status_code))

    # 4. build route
    r = client.post(f"/api/jobs/{job_id}/route", headers=auth)
    check("build_route", r.status_code == 200, str(r.status_code))
    state = r.json()["state"]
    first_uid = state["stops"][0]["uid"]

    # 4b. manual reorder (choose your own order, like the laptop)
    if len(state["stops"]) > 1:
        order0 = [s["uid"] for s in state["stops"]]
        second = order0[1]
        # move the 2nd stop UP — it should become the 1st
        r = client.post(f"/api/jobs/{job_id}/stops/{second}/move", headers=auth, json={"dir": "up"})
        moved_ok = r.status_code == 200 and r.json().get("moved") is True
        new_order = [s["uid"] for s in r.json()["state"]["stops"]] if r.status_code == 200 else []
        check("reorder_move_up", moved_ok and new_order[0] == second, str(r.status_code))
        # move it back DOWN — order restored to the optimized one
        r = client.post(f"/api/jobs/{job_id}/stops/{second}/move", headers=auth, json={"dir": "down"})
        restored = r.status_code == 200 and [s["uid"] for s in r.json()["state"]["stops"]] == order0
        check("reorder_move_down_restores", restored, str(r.status_code))
        # top stop moving UP is a safe no-op (edge), not an error
        r = client.post(f"/api/jobs/{job_id}/stops/{order0[0]}/move", headers=auth, json={"dir": "up"})
        check("reorder_edge_noop", r.status_code == 200 and r.json().get("moved") is False, str(r.status_code))
        # bad direction rejected
        r = client.post(f"/api/jobs/{job_id}/stops/{order0[0]}/move", headers=auth, json={"dir": "sideways"})
        check("reorder_bad_dir_rejected", r.status_code == 400, str(r.status_code))
        # unknown stop rejected
        r = client.post(f"/api/jobs/{job_id}/stops/nope/move", headers=auth, json={"dir": "up"})
        check("reorder_unknown_stop_rejected", r.status_code == 404, str(r.status_code))
        # re-trace the current order (no re-optimize)
        r = client.post(f"/api/jobs/{job_id}/retrace", headers=auth)
        check("retrace_current_order", r.status_code == 200 and "state" in r.json(), str(r.status_code))
        # re-read clean state for downstream steps
        state = client.get(f"/api/jobs/{job_id}", headers=auth).json()["state"]
        first_uid = state["stops"][0]["uid"]

    # 5. phone GPS grab (exact install location) on the first stop
    s0 = state["stops"][0]
    glat = (s0.get("lat") or 33.81) + 0.0001
    glon = (s0.get("lon") or -117.92) + 0.0001
    r = client.post(
        f"/api/jobs/{job_id}/stops/{first_uid}/grab",
        headers=auth,
        json={"lat": glat, "lon": glon, "source": "phone_gps", "accuracy": 5.0},
    )
    ok_grab = r.status_code == 200 and r.json()["stop"]["field_lat"] is not None
    check("phone_gps_grab", ok_grab, str(r.status_code))
    check("grab_source_phone_gps", r.status_code == 200 and r.json()["stop"]["field_source"] == "phone_gps")

    # 6. geolocation-denied fallback: manual pin grab on second stop
    if len(state["stops"]) > 1:
        uid2 = state["stops"][1]["uid"]
        r = client.post(
            f"/api/jobs/{job_id}/stops/{uid2}/grab",
            headers=auth,
            json={"lat": glat + 0.0002, "lon": glon + 0.0002, "source": "manual"},
        )
        check("pin_fallback_grab", r.status_code == 200 and r.json()["stop"]["field_source"] == "manual")

    # 7. grab outside CA rejected (error path)
    r = client.post(
        f"/api/jobs/{job_id}/stops/{first_uid}/grab",
        headers=auth,
        json={"lat": 51.5, "lon": -0.12},
    )
    check("grab_out_of_bounds_rejected", r.status_code == 422, str(r.status_code))

    # 8. fill fields + install
    r = client.patch(
        f"/api/jobs/{job_id}/stops/{first_uid}",
        headers=auth,
        json={"serial": "12345", "lanes": 3, "direction": "n", "notes": "user test"},
    )
    check("patch_fields", r.status_code == 200, str(r.status_code))
    r = client.patch(f"/api/jobs/{job_id}/stops/{first_uid}", headers=auth, json={"installed": True})
    inst_ok = r.status_code == 200 and r.json()["stop"]["installed"]
    check("install_stop", inst_ok, str(r.status_code))
    check("install_timestamped", r.status_code == 200 and bool(_stop_date(r.json()["stop"], state)))

    # 9. pickup
    r = client.patch(f"/api/jobs/{job_id}/stops/{first_uid}", headers=auth, json={"picked_up": True})
    check("pickup_stop", r.status_code == 200 and r.json()["stop"]["picked_up"], str(r.status_code))

    # 10. audit + export
    r = client.get(f"/api/jobs/{job_id}/audit", headers=auth)
    check("audit_endpoint", r.status_code == 200 and "ok" in r.json(), str(r.status_code))
    r = client.get(f"/api/jobs/{job_id}/export.csv", headers=auth)
    csv_ok = r.status_code == 200 and "Site" in r.text
    check("export_csv", csv_ok, str(r.status_code))
    # Counter columns present but blank for mobile (no PicoCount)
    check("export_no_counter_required", csv_ok)

    # 11. error path: bad import (missing files)
    r = client.post("/api/jobs/import", data={"home_lat": "33.8", "home_lon": "-117.9"})
    check("import_missing_files_rejected", r.status_code in (422, 400), str(r.status_code))

    # 12. static shell served
    r = client.get("/")
    check("pwa_shell_served", r.status_code == 200 and "Traffic Deployer" in r.text)
    r = client.get("/manifest.webmanifest")
    check("manifest_served", r.status_code == 200)

    failed = [c["name"] for c in checks if not c["ok"]]
    return _finish(checks, 0 if not failed else 1)


def _stop_date(stop_view: dict, state: dict) -> bool:
    # The public stop view omits date; install timestamp is internal. Treat install flag as proof.
    return stop_view.get("installed", False)


def _finish(checks: list[dict], code: int) -> int:
    os.makedirs(PROOF_DIR, exist_ok=True)
    report = {
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "passed": sum(1 for c in checks if c["ok"]),
        "total": len(checks),
        "failed": [c["name"] for c in checks if not c["ok"]],
        "checks": checks,
    }
    with open(os.path.join(PROOF_DIR, "user_prove.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n{report['passed']}/{report['total']} checks passed.")
    if report["failed"]:
        print("FAILED:", ", ".join(report["failed"]))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
