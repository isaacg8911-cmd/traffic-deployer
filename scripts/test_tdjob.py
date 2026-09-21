"""Portable .tdjob.json pack/unpack + restore API.

Proves:
  - pack/unpack roundtrip keeps install GPS + flags
  - bad files are rejected (error path)
  - POST /api/jobs/restore creates a new job from a snapshot
  - GET /api/jobs/{id}/tdjob downloads that snapshot
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
    from mobile_web.tdjob import FORMAT, TdjobError, pack_job, unpack_job

    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"[{'OK ' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    # --- format: happy + error paths (no server) ---
    sample = {
        "id": "abc123",
        "token": "secret-must-not-leak",
        "label": "Week test",
        "home": [33.81, -117.92],
        "home_label": "Yard",
        "active_files": ["Day5"],
        "route": {"polyline": [[33.81, -117.92], [33.82, -117.91]], "miles": 1.2, "graph": True},
        "stops": [
            {
                "uid": "Day5_101",
                "id": "101",
                "sheet": "Day5",
                "street": "Main St",
                "lat": 33.81,
                "lon": -117.92,
                "serial": "555",
                "lanes": 2,
                "direction": "n",
                "installed": True,
                "skipped": False,
                "picked_up": False,
                "field_lat": 33.8101,
                "field_lon": -117.9201,
                "field_coord_source": "phone_gps",
                "notes": "hose",
                "junk": "drop-me",
            }
        ],
    }
    packed = pack_job(sample)
    check("format_name", packed.get("format") == FORMAT)
    check("token_stripped", "token" not in packed)
    check("junk_stripped", "junk" not in packed["stops"][0])
    check("install_kept", packed["stops"][0]["installed"] is True)
    check("gps_kept", packed["stops"][0]["field_lat"] == 33.8101)

    data = unpack_job(packed)
    check("unpack_stops", len(data["stops"]) == 1 and data["stops"][0]["uid"] == "Day5_101")
    check("unpack_home", data["home"] == (33.81, -117.92))

    def expect_err(name: str, payload) -> None:
        try:
            unpack_job(payload)
            check(name, False, "expected TdjobError")
        except TdjobError:
            check(name, True)

    expect_err("reject_not_object", [])
    expect_err("reject_wrong_format", {"format": "nope", "version": 1, "stops": sample["stops"]})
    expect_err("reject_empty_stops", {"format": FORMAT, "version": 1, "stops": []})
    expect_err("reject_bad_version", {"format": FORMAT, "version": 99, "stops": sample["stops"]})

    # --- API restore ---
    client = TestClient(app)
    r = client.post("/api/jobs/demo")
    check("demo_job", r.status_code == 200, str(r.status_code))
    if r.status_code != 200:
        return _finish(checks, 1)
    job_id, token = r.json()["job_id"], r.json()["token"]
    auth = {"x-job-token": token}

    first_uid = r.json()["state"]["stops"][0]["uid"]
    client.patch(
        f"/api/jobs/{job_id}/stops/{first_uid}",
        headers=auth,
        json={"serial": "99901", "installed": True, "street": "Harbor Blvd"},
    )
    client.post(
        f"/api/jobs/{job_id}/stops/{first_uid}/grab",
        headers=auth,
        json={"lat": 33.8102, "lon": -117.9202, "source": "phone_gps", "accuracy": 4},
    )

    r = client.get(f"/api/jobs/{job_id}/tdjob", headers=auth)
    check("download_tdjob", r.status_code == 200 and r.json().get("format") == FORMAT, str(r.status_code))
    snapshot = r.json()
    check("download_has_install", any(s.get("installed") for s in snapshot.get("stops") or []))

    r = client.get(f"/api/jobs/{job_id}/tdjob", headers={"x-job-token": "wrong"})
    check("tdjob_token_enforced", r.status_code == 404, str(r.status_code))

    r = client.post("/api/jobs/restore", json={"format": "nope", "version": 1, "stops": []})
    check("restore_bad_file_rejected", r.status_code == 422, str(r.status_code))

    r = client.post("/api/jobs/restore", json=snapshot)
    check("restore_ok", r.status_code == 200, str(r.status_code))
    if r.status_code != 200:
        return _finish(checks, 1)
    body = r.json()
    new_id, new_tok = body["job_id"], body["token"]
    check("restore_new_id", new_id != job_id, f"{new_id} vs {job_id}")
    check("restore_new_token", new_tok != token)

    r = client.get(f"/api/jobs/{new_id}", headers={"x-job-token": new_tok})
    stops = r.json()["state"]["stops"] if r.status_code == 200 else []
    restored = next((s for s in stops if s.get("serial") == "99901"), None)
    check("restore_serial", restored is not None and restored.get("installed"), str(bool(restored)))
    check(
        "restore_field_gps",
        restored is not None and restored.get("field_lat") is not None,
        str(restored.get("field_lat") if restored else None),
    )

    # PWA shell still mentions laptop-like tabs + job file pickup
    r = client.get("/")
    html = r.text if r.status_code == 200 else ""
    check("pwa_has_setup_tab", "data-tab=\"setup\"" in html)
    check("pwa_has_tdjob_input", "impTdjob" in html)
    check("pwa_loads_local_js", "local.js" in html)
    r = client.get("/local.js")
    check("local_js_served", r.status_code == 200 and "traffic-deployer-job" in r.text, str(r.status_code))

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
    with open(os.path.join(PROOF_DIR, "tdjob_prove.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n{report['passed']}/{report['total']} checks passed.")
    if report["failed"]:
        print("FAILED:", ", ".join(report["failed"]))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
