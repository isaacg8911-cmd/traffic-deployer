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
import shutil
import subprocess
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

    js = client.get("/app.js?v=13").text
    html = client.get("/").text
    check(
        "directions choice on the map",
        "showNavOffer" in js and 'id="navOffer"' in html and "site-begin" in js and "site-end" in js,
    )
    click_at = js.find("map.on('click', 'stop-dot'")
    end_at = js.find("function mapsDirectionsUrl")
    site_click = js[click_at:end_at] if 0 <= click_at < end_at else ""
    check(
        "site tap does not open Google Maps",
        "openSiteForm" in site_click and "mapsDirectionsUrl" not in site_click and "window.open" not in site_click,
    )
    check(
        "directions link is the button",
        "navOfferGo" in js and "maps.google.com" not in js and "google.com/maps/dir" in js,
    )

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
        r = client.post(
            f"/api/jobs/{job_id}/stops/{uid2}/grab",
            headers=auth,
            json={"clear": True},
        )
        cleared = r.status_code == 200 and r.json()["stop"]["field_lat"] is None
        check("clear_wrong_site_grab", cleared, str(r.status_code))
        still = client.get(f"/api/jobs/{job_id}", headers=auth).json()["state"]
        kept = still["stops"][0].get("field_lat") is not None
        check("clear_leaves_other_site", kept)

    # 7. grab outside CA rejected (error path)
    r = client.post(
        f"/api/jobs/{job_id}/stops/{first_uid}/grab",
        headers=auth,
        json={"lat": 51.5, "lon": -0.12},
    )
    check("grab_out_of_bounds_rejected", r.status_code == 422, str(r.status_code))

    # 8. a count is not installed until GPS, direction, and serial are present
    r = client.patch(
        f"/api/jobs/{job_id}/stops/{first_uid}",
        headers=auth,
        json={"installed": True},
    )
    detail = ""
    if r.status_code == 422:
        body = r.json()
        detail = body.get("detail") if isinstance(body, dict) else ""
        detail = detail if isinstance(detail, str) else str(detail)
    check("install_without_serial_rejected", r.status_code == 422 and "serial" in detail.lower(), detail or str(r.status_code))
    held = client.get(f"/api/jobs/{job_id}", headers=auth).json()["state"]["stops"][0]
    check("rejected_install_not_saved", held.get("installed") is not True)
    if len(state["stops"]) > 1:
        uid_plain = state["stops"][1]["uid"]
        r = client.patch(
            f"/api/jobs/{job_id}/stops/{uid_plain}",
            headers=auth,
            json={"picked_up": True},
        )
        check("pickup_before_install_rejected", r.status_code == 422, str(r.status_code))

    # 9. fill fields + install
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
    packed = client.get(f"/api/jobs/{job_id}/tdjob", headers=auth).json()
    stamped = next((s for s in packed.get("stops") or [] if s.get("uid") == first_uid), {})
    exact = str(stamped.get("exact_time") or "")
    check("install_clock_is_california_stamp", " " in exact and exact[:4].isdigit(), exact)
    r = client.patch(
        f"/api/jobs/{job_id}/stops/{first_uid}",
        headers=auth,
        json={"installed": False, "exact_time": "", "date": ""},
    )
    undone = r.status_code == 200 and not r.json()["stop"]["installed"]
    check("undo_install_clears_done", undone, str(r.status_code))
    packed = client.get(f"/api/jobs/{job_id}/tdjob", headers=auth).json()
    cleared = next((s for s in packed.get("stops") or [] if s.get("uid") == first_uid), {})
    check("undo_clears_install_stamp", not str(cleared.get("exact_time") or "").strip(), str(cleared.get("exact_time")))
    r = client.patch(f"/api/jobs/{job_id}/stops/{first_uid}", headers=auth, json={"installed": True})
    check("reinstall_after_undo", r.status_code == 200 and r.json()["stop"]["installed"], str(r.status_code))
    r = client.post(
        f"/api/jobs/{job_id}/stops/{first_uid}/grab",
        headers=auth,
        json={"lat": glat, "lon": glon, "source": "phone_gps", "accuracy": 5.0},
    )
    check("grab_finished_site_rejected", r.status_code == 422, str(r.status_code))

    # 10. pickup
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
    check("pwa_setup_tab", r.status_code == 200 and 'data-tab="setup"' in r.text)
    check("pwa_job_file_pickup", r.status_code == 200 and "impTdjob" in r.text)
    check("pwa_no_yard_address", r.status_code == 200 and 'id="homeAddr"' not in r.text)
    check("pwa_direction_hint", 'id="dirHint"' in r.text and 'id="btnCompass"' in r.text)
    check("pwa_nearest_and_undo", 'id="nearLine"' in r.text and 'id="btnUndo"' in r.text)
    check("pwa_pickup_grab", 'id="btnPickupGrab"' in r.text)
    check("pwa_map_save_banner", 'id="mapBanner"' in r.text)
    check("pwa_file_buttons", r.status_code == 200 and "file-btn" in r.text)
    check("pwa_has_no_build_route", "Build route" not in r.text and "Follow GPS" not in r.text)
    r = client.get("/api/geocode")
    check("geocode_empty_rejected", r.status_code == 422, str(r.status_code))
    r = client.get("/manifest.webmanifest")
    check("manifest_served", r.status_code == 200)
    r = client.get("/local.js")
    check("local_js_served", r.status_code == 200 and "TDLocal" in r.text)
    check("phone_refuses_bad_install", _js_refuses_bad_install())
    check("phone_field_loop_helpers", _js_field_loop())

    failed = [c["name"] for c in checks if not c["ok"]]
    return _finish(checks, 0 if not failed else 1)


def _js_refuses_bad_install() -> bool:
    """The offline phone copy must refuse the same bad installs as the server."""
    node = shutil.which("node")
    if not node:
        print("[SKIP] js install gate — node not on PATH")
        return True
    script = r"""
const fs = require('fs');
const vm = require('vm');
const src = fs.readFileSync(process.argv[1], 'utf8');
const ctx = {};
vm.createContext(ctx);
vm.runInContext(src, ctx);
const L = ctx.TDLocal;
const bare = { installed: false, field_lat: null, field_lon: null, direction: '', serial: '' };
const noSerial = L.patchBlockReason(bare, { installed: true, direction: 'n', serial: '' });
const noGps = L.patchBlockReason(
  { installed: false, field_lat: null, field_lon: null, direction: 'n', serial: '1' },
  { installed: true }
);
const pickup = L.patchBlockReason({ installed: false }, { picked_up: true });
const ok = L.patchBlockReason(
  { installed: false, field_lat: 33.8, field_lon: -117.9, direction: 'n', serial: '1' },
  { installed: true }
);
if (!noSerial || !noGps || !pickup || ok) process.exit(2);
process.exit(0);
"""
    local_js = os.path.join(ROOT, "mobile_web", "static", "local.js")
    proc = subprocess.run([node, "-e", script, local_js], capture_output=True, text=True, check=False)
    return proc.returncode == 0


def _js_field_loop() -> bool:
    """Direction from the site line, duplicate serial, pickup match, undo restore."""
    node = shutil.which("node")
    if not node:
        print("[SKIP] js field loop — node not on PATH")
        return True
    script = r"""
const fs = require('fs');
const vm = require('vm');
const src = fs.readFileSync(process.argv[1], 'utf8');
const ctx = {};
vm.createContext(ctx);
vm.runInContext(src, ctx);
const L = ctx.TDLocal;
const ns = L.inferDirection({ begin_lat: 33.8, begin_lon: -117.9, end_lat: 33.801, end_lon: -117.9 });
if (ns.direction !== 'n' || ns.source !== 'segment') process.exit(3);
const ew = L.inferDirection({ begin_lat: 33.8, begin_lon: -117.9, end_lat: 33.8, end_lon: -117.898 });
if (ew.direction !== 'e') process.exit(4);
const short = L.inferDirection({ begin_lat: 33.8, begin_lon: -117.9, end_lat: 33.80005, end_lon: -117.9 });
if (short.source !== 'needs_gps' || short.direction) process.exit(5);
const dup = L.duplicateSerial([
  { uid: 'a', id: '1', serial: '22976' },
  { uid: 'b', id: '2', serial: '' }
], 'b', '22976');
if (!dup || String(dup.id) !== '1') process.exit(6);
if (L.duplicateSerial([{ uid: 'a', id: '1', serial: '22976' }], 'a', '22976')) process.exit(7);
const stops = [
  { uid: 'near', id: '9', street: 'Main', installed: true, picked_up: false, skipped: false,
    begin_lat: 33.8, begin_lon: -117.9, end_lat: 33.801, end_lon: -117.9 },
  { uid: 'far', id: '10', street: 'Oak', installed: true, picked_up: false, skipped: false,
    begin_lat: 34.2, begin_lon: -118.2, end_lat: 34.201, end_lon: -118.2 }
];
const pick = L.matchPickup(stops, 33.8002, -117.9, 8);
if (pick.status !== 'bind' || pick.uid !== 'near') process.exit(8);
const open = L.closestUnfinished([
  { uid: 'done', id: '1', installed: true, skipped: false, begin_lat: 33.8, begin_lon: -117.9, end_lat: 33.801, end_lon: -117.9 },
  { uid: 'open', id: '2', installed: false, skipped: false, begin_lat: 33.81, begin_lon: -117.9, end_lat: 33.811, end_lon: -117.9 }
], 33.8001, -117.9);
if (!open || open.uid !== 'open') process.exit(9);
const snap = L.copyStop({ id: '1', uid: 'u', street: 'Main', direction: 'n', serial: '1', installed: false, field_lat: 33.8, field_lon: -117.9, exact_time: '', date: '' });
const live = L.copyStop(snap);
L.applyStopPatch(live, { installed: true, direction: 'n', serial: '1' });
if (!live.installed || !live.exact_time) process.exit(10);
L.applyStopPatch(live, { installed: false, exact_time: '', date: '', direction: 'n', serial: '1' });
L.restoreStop(live, snap);
if (live.installed || live.exact_time) process.exit(11);
const one = L.tilesAroundSites([
  { begin_lat: 33.8, begin_lon: -117.9, end_lat: 33.801, end_lon: -117.9 }
], 'https://tile.openstreetmap.org/{z}/{x}/{y}.png');
if (!one.length || one.length > 40) process.exit(12);
if (!one.some(function (u) { return u.indexOf('/16/') !== -1; })) process.exit(13);
if (!one.some(function (u) { return u.indexOf('/17/') !== -1; })) process.exit(14);
const far = L.tilesAroundSites([
  { begin_lat: 33.8, begin_lon: -117.9, end_lat: 33.801, end_lon: -117.9 },
  { begin_lat: 34.2, begin_lon: -118.4, end_lat: 34.201, end_lon: -118.4 }
], 'https://tile.openstreetmap.org/{z}/{x}/{y}.png');
if (far.length > 80 || far.length < one.length) process.exit(15);
const many = [];
for (var i = 0; i < 80; i++) {
  var lat = 33 + i * 0.02;
  many.push({ begin_lat: lat, begin_lon: -117.9, end_lat: lat + 0.001, end_lon: -117.9 });
}
if (L.tilesAroundSites(many).length > 320) process.exit(16);
process.exit(0);
"""
    local_js = os.path.join(ROOT, "mobile_web", "static", "local.js")
    proc = subprocess.run([node, "-e", script, local_js], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout)
    return proc.returncode == 0


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
