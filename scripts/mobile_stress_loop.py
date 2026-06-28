"""Mobile stress loop — exercise the API under load; log latency + weaknesses.

Scenarios (in-process ASGI, no network):
  - full install cycle over every stop
  - rapid map-state polls (latency p50/p95)
  - concurrent grab + patch on the same stop (race / lost-update check)
  - large synthetic job (route + map-state payload size)

Logs: logs/mobile_stress/YYYY-MM-DD.jsonl  (same shape as desktop stress_loop)
Exit 0 = no required scenario failed.
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LOG_DIR = os.path.join(ROOT, "logs", "mobile_stress")

# Latency budget (ms) for the in-process harness. The TestClient/ASGI portal adds
# fixed per-call overhead on Windows, so this measures handler cost + that floor;
# real network adds RTT on top. Tracked so regressions are visible.
MAP_STATE_P95_BUDGET_MS = 250.0


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = int(round((p / 100.0) * (len(values) - 1)))
    return values[k]


def run(cycles: int) -> tuple[bool, dict]:
    from fastapi.testclient import TestClient

    from mobile_web.server import app, store

    client = TestClient(app)
    scenarios: list[dict] = []

    def record(name: str, ok: bool, metrics: dict, required: bool = True) -> None:
        scenarios.append({"name": name, "ok": ok, "required": required, "metrics": metrics})
        flag = "OK " if ok else "FAIL"
        print(f"[{flag}] {name} {metrics}")

    # ---- demo job
    r = client.post("/api/jobs/demo")
    if r.status_code != 200:
        record("setup_demo", False, {"status": r.status_code})
        return False, _summary(scenarios)
    body = r.json()
    job_id, token = body["job_id"], body["token"]
    auth = {"x-job-token": token}
    client.post(f"/api/jobs/{job_id}/route", headers=auth)

    state = client.get(f"/api/jobs/{job_id}/map-state", headers=auth).json()
    uids = [s["uid"] for s in state["stops"]]

    # ---- scenario 1: full install cycle
    t0 = time.perf_counter()
    install_fail = 0
    for i, uid in enumerate(uids):
        rg = client.post(f"/api/jobs/{job_id}/stops/{uid}/grab", headers=auth,
                         json={"lat": 33.81 + i * 1e-4, "lon": -117.92 - i * 1e-4, "source": "phone_gps"})
        rp = client.patch(f"/api/jobs/{job_id}/stops/{uid}", headers=auth,
                         json={"serial": str(1000 + i), "installed": True})
        if rg.status_code != 200 or rp.status_code != 200:
            install_fail += 1
    counts = client.get(f"/api/jobs/{job_id}/map-state", headers=auth).json()["counts"]
    install_ok = install_fail == 0 and counts["installed"] == len(uids)
    record("install_cycle", install_ok,
           {"stops": len(uids), "installed": counts["installed"], "fails": install_fail,
            "ms": round((time.perf_counter() - t0) * 1000, 1)})

    # ---- scenario 2: rapid map-state polls
    polls = max(50, 20 * cycles)
    lat: list[float] = []
    for _ in range(polls):
        s = time.perf_counter()
        rr = client.get(f"/api/jobs/{job_id}/map-state", headers=auth)
        lat.append((time.perf_counter() - s) * 1000)
        if rr.status_code != 200:
            break
    p50, p95 = _pct(lat, 50), _pct(lat, 95)
    record("rapid_map_state", p95 <= MAP_STATE_P95_BUDGET_MS,
           {"polls": polls, "p50_ms": round(p50, 1), "p95_ms": round(p95, 1),
            "budget_ms": MAP_STATE_P95_BUDGET_MS})

    # ---- scenario 3: concurrent grab + patch on the SAME stop (race check)
    race_uid = uids[0]
    errors: list[str] = []

    def hammer(idx: int) -> None:
        try:
            client.post(f"/api/jobs/{job_id}/stops/{race_uid}/grab", headers=auth,
                       json={"lat": 33.8 + idx * 1e-5, "lon": -117.9, "source": "manual"})
            client.patch(f"/api/jobs/{job_id}/stops/{race_uid}", headers=auth,
                        json={"notes": f"t{idx}"})
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    threads = [threading.Thread(target=hammer, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    after = store.load(job_id)
    intact = after is not None and len(after["stops"]) == len(uids)
    record("concurrent_writes", not errors and intact,
           {"threads": 10, "errors": len(errors), "stops_intact": intact})

    # ---- scenario 4: large synthetic job — payload size + edit latency under volume.
    # (Street-tracing 80 stops is a known heavy desktop-grade cost and depends on a
    #  server road graph; the lean phone server ships none. We measure what the phone
    #  actually hits: map-state payload and per-stop edit latency.)
    big = _make_big_job(store, n=80)
    bauth = {"x-job-token": big["token"]}
    ms = client.get(f"/api/jobs/{big['id']}/map-state", headers=bauth)
    payload_kb = round(len(ms.content) / 1024, 1)
    edit_lat: list[float] = []
    for s in ms.json()["stops"][:20]:
        t = time.perf_counter()
        client.patch(f"/api/jobs/{big['id']}/stops/{s['uid']}", headers=bauth, json={"serial": "9"})
        edit_lat.append((time.perf_counter() - t) * 1000)
    record("large_job_80", ms.status_code == 200,
           {"stops": 80, "map_state_kb": payload_kb, "edit_p95_ms": round(_pct(edit_lat, 95), 1)},
           required=False)

    # ---- scenario 5: rapid manual reorder — hammer move up/down + re-trace.
    # Proves the order edits never drop/duplicate a stop and stay responsive
    # under fast field taps.
    reorder_lat: list[float] = []
    reorder_errors = 0
    moves = max(40, 30 * cycles)
    for i in range(moves):
        if len(uids) < 2:
            break
        target = uids[(i + 1) % len(uids)]
        direction = "up" if i % 2 == 0 else "down"
        t = time.perf_counter()
        rm = client.post(f"/api/jobs/{job_id}/stops/{target}/move", headers=auth,
                         json={"dir": direction})
        reorder_lat.append((time.perf_counter() - t) * 1000)
        if rm.status_code != 200:
            reorder_errors += 1
    rt = client.post(f"/api/jobs/{job_id}/retrace", headers=auth)
    final = client.get(f"/api/jobs/{job_id}/map-state", headers=auth).json()
    final_uids = sorted(s["uid"] for s in final["stops"])
    no_loss = final_uids == sorted(uids)
    record("rapid_reorder", reorder_errors == 0 and no_loss and rt.status_code == 200,
           {"moves": moves, "errors": reorder_errors, "stops_intact": no_loss,
            "p95_ms": round(_pct(reorder_lat, 95), 1)})

    # cleanup synthetic + demo
    store.delete(big["id"])
    store.delete(job_id)

    return _all_ok(scenarios), _summary(scenarios)


def _make_big_job(store, n: int) -> dict:
    from core import ingest

    stops = []
    base_lat, base_lon = 33.80, -117.95
    for i in range(n):
        data = {
            "begin_lat": base_lat + (i % 10) * 0.003,
            "begin_lon": base_lon + (i // 10) * 0.003,
            "end_lat": base_lat + (i % 10) * 0.003 + 0.0008,
            "end_lon": base_lon + (i // 10) * 0.003 + 0.0008,
            "lat": base_lat + (i % 10) * 0.003 + 0.0004,
            "lon": base_lon + (i // 10) * 0.003 + 0.0004,
            "street": f"Synthetic St {i}",
        }
        stops.append(ingest.new_stop(str(10000 + i), "Stress", data))
    return store.create(home=(base_lat, base_lon), home_label="stress",
                        stops=stops, active_files=["Stress"], label="stress 80")


def _all_ok(scenarios: list[dict]) -> bool:
    return not [s for s in scenarios if s["required"] and not s["ok"]]


def _summary(scenarios: list[dict]) -> dict:
    return {
        "scenarios": scenarios,
        "failed_required": [s["name"] for s in scenarios if s["required"] and not s["ok"]],
        "failed_optional": [s["name"] for s in scenarios if not s["required"] and not s["ok"]],
    }


def _append_log(record: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(os.path.join(LOG_DIR, f"{day}.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mobile stress loop")
    parser.add_argument("--cycles", type=int, default=1)
    args = parser.parse_args()

    from version import APP_VERSION

    t0 = time.perf_counter()
    ok, summary = run(args.cycles)
    rec = {
        "when": datetime.now(timezone.utc).isoformat(),
        "version": APP_VERSION,
        "pass": ok,
        "seconds": round(time.perf_counter() - t0, 1),
        **summary,
    }
    _append_log(rec)
    print(f"\nStress {'PASS' if ok else 'FAIL'} in {rec['seconds']}s")
    if summary["failed_required"]:
        print("Failed:", ", ".join(summary["failed_required"]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
