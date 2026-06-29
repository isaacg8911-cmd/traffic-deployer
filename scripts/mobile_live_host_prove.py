"""Live-host prove: user flow + stress against a deployed mobile PWA URL.

Usage:
  python scripts/mobile_live_host_prove.py --base https://tds-field-app.onrender.com
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
from datetime import datetime, timezone

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROOF_DIR = os.path.join(ROOT, "logs", "mobile_check", "proofs")

MAP_STATE_P95_BUDGET_MS = 800.0  # live network RTT on free Render; in-process budget is ~250ms
ROUTE_BUILD_BUDGET_S = 45.0


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = int(round((p / 100.0) * (len(values) - 1)))
    return values[k]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="e.g. https://tds-field-app.onrender.com")
    parser.add_argument("--admin-key", default=os.environ.get("TD_MOBILE_ADMIN_KEY", ""))
    parser.add_argument(
        "--open-create",
        action="store_true",
        help="Expect TD_MOBILE_OPEN_CREATE=1 (demo without admin key allowed)",
    )
    parser.add_argument("--cycles", type=int, default=2, help="stress repeat factor")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    admin_h = {"x-admin-key": args.admin_key} if args.admin_key else {}

    user_checks: list[dict] = []
    stress: list[dict] = []

    def ucheck(name: str, ok: bool, detail: str = "", ms: float | None = None) -> None:
        row = {"name": name, "ok": bool(ok), "detail": detail}
        if ms is not None:
            row["ms"] = round(ms, 1)
        user_checks.append(row)
        flag = "OK " if ok else "FAIL"
        extra = f" ({detail})" if detail else ""
        timing = f" [{row.get('ms')}ms]" if ms is not None else ""
        print(f"[USER {flag}] {name}{extra}{timing}")

    def srecord(name: str, ok: bool, metrics: dict, required: bool = True) -> None:
        stress.append({"name": name, "ok": ok, "required": required, "metrics": metrics})
        flag = "OK " if ok else "FAIL"
        print(f"[STRESS {flag}] {name} {metrics}")

    timeout = httpx.Timeout(60.0, connect=30.0)
    with httpx.Client(base_url=base, timeout=timeout, follow_redirects=True) as client:
        # ---- cold wake
        t0 = time.perf_counter()
        r = client.get("/api/healthz")
        cold_ms = (time.perf_counter() - t0) * 1000
        ucheck("cold_health", r.status_code == 200 and r.json().get("ok"), str(r.status_code), cold_ms)

        r = client.get("/api/config")
        cfg = r.json() if r.status_code == 200 else {}
        ucheck("config_ok", r.status_code == 200, str(r.status_code))
        ucheck("public_mode", cfg.get("public_mode") is True)
        can_create = bool(cfg.get("can_create"))
        if args.open_create:
            ucheck("open_create", can_create is True, "can_create")
        else:
            ucheck("creation_gated", can_create is False, f"can_create={can_create}")

        # ---- PWA shell
        r = client.get("/")
        ucheck("pwa_shell", r.status_code == 200 and "Traffic Deployer" in r.text)
        import re
        js_ver = re.search(r"app\.js\?v=(\d+)", r.text)
        js_v = js_ver.group(1) if js_ver else ""
        ucheck("app_js_versioned", bool(js_v), f"v={js_v or 'missing'}")
        r = client.get(f"/app.js?v={js_v}" if js_v else "/app.js")
        ucheck("no_route_line_layer", r.status_code == 200 and "route-line" not in r.text)
        ucheck("no_retrace_button", r.status_code == 200 and "btnRetrace" not in r.text)
        ucheck("remember_job_fix", r.status_code == 200 and "publicMode && !state.canCreate" in r.text)

        # ---- job creation posture
        t0 = time.perf_counter()
        r = client.post("/api/jobs/demo")
        demo_ms = (time.perf_counter() - t0) * 1000
        if args.open_create:
            ucheck("demo_no_key", r.status_code == 200, str(r.status_code), demo_ms)
        else:
            ucheck("demo_blocked_no_key", r.status_code == 403, str(r.status_code), demo_ms)
            if not args.admin_key:
                print("[WARN] --admin-key not set; cannot continue share-only live prove.")
                return _finish(base, user_checks, stress, 1)
            t0 = time.perf_counter()
            r = client.post("/api/jobs/demo", headers=admin_h)
            demo_ms = (time.perf_counter() - t0) * 1000
            ucheck("demo_with_admin_key", r.status_code == 200, str(r.status_code), demo_ms)
        if r.status_code != 200:
            return _finish(base, user_checks, stress, 1)
        body = r.json()
        job_id, token = body["job_id"], body["token"]
        auth = {"x-job-token": token}
        share_url = body.get("share_url", "")
        ucheck("share_url", bool(share_url) and f"/join/{job_id}" in share_url, share_url[:80])

        # ---- import guard (no files)
        r = client.post("/api/jobs/import", data={})
        ucheck("import_missing_files", r.status_code == 422, r.text[:120])

        # ---- token enforcement
        r = client.get(f"/api/jobs/{job_id}", headers={"x-job-token": "bad"})
        ucheck("token_enforced", r.status_code == 404, str(r.status_code))

        # ---- build route (live server, no road graph expected)
        t0 = time.perf_counter()
        r = client.post(f"/api/jobs/{job_id}/route", headers=auth)
        route_s = time.perf_counter() - t0
        ucheck("build_route", r.status_code == 200 and route_s < ROUTE_BUILD_BUDGET_S,
               f"status={r.status_code} t={route_s:.1f}s", route_s * 1000)
        state = r.json()["state"]
        first_uid = state["stops"][0]["uid"]
        uids = [s["uid"] for s in state["stops"]]

        # ---- reorder without any map line tracing
        if len(uids) > 1:
            second = uids[1]
            r = client.post(f"/api/jobs/{job_id}/stops/{second}/move", headers=auth, json={"dir": "up"})
            ucheck("reorder_up", r.status_code == 200 and r.json().get("moved") is True)
            r = client.post(f"/api/jobs/{job_id}/stops/{second}/move", headers=auth, json={"dir": "down"})
            ucheck("reorder_restore", r.status_code == 200)

        # ---- grab / install / pickup
        s0 = state["stops"][0]
        glat = (s0.get("lat") or 33.81) + 0.0001
        glon = (s0.get("lon") or -117.92) + 0.0001
        r = client.post(
            f"/api/jobs/{job_id}/stops/{first_uid}/grab",
            headers=auth,
            json={"lat": glat, "lon": glon, "source": "phone_gps", "accuracy": 5.0},
        )
        ucheck("phone_gps_grab", r.status_code == 200 and r.json()["stop"]["field_lat"] is not None)
        r = client.post(
            f"/api/jobs/{job_id}/stops/{first_uid}/grab",
            headers=auth,
            json={"lat": 51.5, "lon": -0.12},
        )
        ucheck("grab_oob_rejected", r.status_code == 422)
        r = client.patch(
            f"/api/jobs/{job_id}/stops/{first_uid}",
            headers=auth,
            json={"serial": "99999", "lanes": 3, "direction": "n", "installed": True},
        )
        ucheck("install_stop", r.status_code == 200 and r.json()["stop"]["installed"])
        r = client.patch(f"/api/jobs/{job_id}/stops/{first_uid}", headers=auth, json={"picked_up": True})
        ucheck("pickup_stop", r.status_code == 200 and r.json()["stop"]["picked_up"])

        # ---- audit + export
        r = client.get(f"/api/jobs/{job_id}/audit", headers=auth)
        ucheck("audit", r.status_code == 200 and "ok" in r.json())
        r = client.get(f"/api/jobs/{job_id}/export.csv", headers=auth)
        ucheck("export_csv", r.status_code == 200 and "Site" in r.text)

        # ---- share link opens job (simulate crew phone)
        r = client.get(f"/api/jobs/{job_id}", headers=auth)
        ucheck("share_open_job", r.status_code == 200 and r.json()["state"]["counts"]["total"] > 0)
        r = client.get(f"/join/{job_id}", params={"token": token})
        ucheck("join_shell", r.status_code == 200 and "Traffic Deployer" in r.text)
        r = client.get(f"/api/jobs/{job_id}/share.svg", headers=auth)
        ucheck("share_qr", r.status_code == 200 and "svg" in (r.headers.get("content-type") or ""))

        # ========== STRESS ==========
        polls = max(30, 25 * args.cycles)
        lat: list[float] = []
        poll_fail = 0
        for _ in range(polls):
            s = time.perf_counter()
            rr = client.get(f"/api/jobs/{job_id}/map-state", headers=auth)
            lat.append((time.perf_counter() - s) * 1000)
            if rr.status_code != 200:
                poll_fail += 1
        p50, p95 = _pct(lat, 50), _pct(lat, 95)
        srecord(
            "rapid_map_state",
            poll_fail == 0 and p95 <= MAP_STATE_P95_BUDGET_MS,
            {"polls": polls, "failures": poll_fail, "p50_ms": round(p50, 1),
             "p95_ms": round(p95, 1), "budget_ms": MAP_STATE_P95_BUDGET_MS},
        )

        # full install cycle on remaining stops
        t0 = time.perf_counter()
        install_fail = 0
        for i, uid in enumerate(uids):
            if uid == first_uid:
                continue
            rg = client.post(
                f"/api/jobs/{job_id}/stops/{uid}/grab",
                headers=auth,
                json={"lat": 33.81 + i * 1e-4, "lon": -117.92 - i * 1e-4, "source": "phone_gps"},
            )
            rp = client.patch(
                f"/api/jobs/{job_id}/stops/{uid}",
                headers=auth,
                json={"serial": str(2000 + i), "installed": True},
            )
            if rg.status_code != 200 or rp.status_code != 200:
                install_fail += 1
        counts = client.get(f"/api/jobs/{job_id}/map-state", headers=auth).json()["counts"]
        srecord(
            "install_cycle",
            install_fail == 0 and counts["installed"] == len(uids),
            {"stops": len(uids), "installed": counts["installed"], "fails": install_fail,
             "ms": round((time.perf_counter() - t0) * 1000, 1)},
        )

        # concurrent hammer (modest — free tier)
        race_uid = first_uid
        errors: list[str] = []

        def hammer(idx: int) -> None:
            try:
                with httpx.Client(base_url=base, timeout=timeout) as c:
                    c.post(
                        f"/api/jobs/{job_id}/stops/{race_uid}/grab",
                        headers=auth,
                        json={"lat": 33.8 + idx * 1e-5, "lon": -117.9, "source": "manual"},
                    )
                    c.patch(
                        f"/api/jobs/{job_id}/stops/{race_uid}",
                        headers=auth,
                        json={"notes": f"t{idx}"},
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))

        threads = [threading.Thread(target=hammer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        after = client.get(f"/api/jobs/{job_id}/map-state", headers=auth)
        intact = after.status_code == 200 and len(after.json().get("stops", [])) == len(uids)
        srecord("concurrent_writes", not errors and intact,
                {"threads": 8, "errors": len(errors), "stops_intact": intact})

        # rapid reorder hammer
        reorder_errors = 0
        reorder_lat: list[float] = []
        moves = max(20, 15 * args.cycles)
        for i in range(moves):
            if len(uids) < 2:
                break
            target = uids[(i + 1) % len(uids)]
            direction = "up" if i % 2 == 0 else "down"
            s = time.perf_counter()
            rm = client.post(
                f"/api/jobs/{job_id}/stops/{target}/move",
                headers=auth,
                json={"dir": direction},
            )
            reorder_lat.append((time.perf_counter() - s) * 1000)
            if rm.status_code != 200:
                reorder_errors += 1
        final = client.get(f"/api/jobs/{job_id}/map-state", headers=auth).json()
        final_uids = sorted(s["uid"] for s in final["stops"])
        no_loss = final_uids == sorted(uids)
        srecord(
            "rapid_reorder",
            reorder_errors == 0 and no_loss,
            {"moves": moves, "errors": reorder_errors, "stops_intact": no_loss,
             "p95_ms": round(_pct(reorder_lat, 95), 1)},
        )

    return _finish(base, user_checks, stress, 0 if _all_pass(user_checks, stress) else 1)


def _all_pass(user_checks: list[dict], stress: list[dict]) -> bool:
    user_ok = all(c["ok"] for c in user_checks)
    stress_ok = not [s for s in stress if s["required"] and not s["ok"]]
    return user_ok and stress_ok


def _finish(base: str, user_checks: list[dict], stress: list[dict], code: int) -> int:
    os.makedirs(PROOF_DIR, exist_ok=True)
    failed_user = [c["name"] for c in user_checks if not c["ok"]]
    failed_stress = [s["name"] for s in stress if s["required"] and not s["ok"]]
    report = {
        "when": datetime.now(timezone.utc).isoformat(),
        "base": base,
        "user": {
            "passed": sum(1 for c in user_checks if c["ok"]),
            "total": len(user_checks),
            "failed": failed_user,
            "checks": user_checks,
        },
        "stress": {
            "pass": not failed_stress,
            "failed_required": failed_stress,
            "scenarios": stress,
        },
        "pass": code == 0,
    }
    out = os.path.join(PROOF_DIR, "live_render_prove.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n=== LIVE HOST {'PASS' if code == 0 else 'FAIL'} ===")
    print(f"User: {report['user']['passed']}/{report['user']['total']}")
    if failed_user:
        print("User failed:", ", ".join(failed_user))
    if failed_stress:
        print("Stress failed:", ", ".join(failed_stress))
    print(f"Proof: {out}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
