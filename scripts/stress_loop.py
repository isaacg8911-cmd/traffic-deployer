"""Regression stress loop — run after every change; log weaknesses for learning.

Usage:
  .venv\\Scripts\\python.exe scripts\\stress_loop.py           # one cycle
  .venv\\Scripts\\python.exe scripts\\stress_loop.py --cycles 3
  .venv\\Scripts\\python.exe scripts\\stress_loop.py --full    # includes smoke_full (~3 min)

Logs: logs/stress/YYYY-MM-DD.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
if not os.path.isfile(PY):
    PY = sys.executable

LOG_DIR = os.path.join(ROOT, "logs", "stress")

STEPS = [
    ("quick_preflight", "scripts/quick_preflight.py", True),
    ("test_home_save", "scripts/test_home_save.py", True),
    ("test_ui_wiring", "scripts/test_ui_wiring.py", True),
    ("test_job_route_audit", "scripts/test_job_route_audit.py", True),
    ("test_field_sim", "scripts/test_field_sim.py", True),
    ("verify_handoff_freshness", "scripts/verify_handoff_freshness.py", True),
    ("verify_frozen_bundle", "scripts/verify_frozen_bundle.py", True),
    ("grab_gps_safe", "scripts/test_grab_gps_safe.py", True),
    ("demo_workflow", "scripts/demo_workflow.py", True),
    ("golden_routes", "scripts/golden_routes.py", True),
    ("benchmark_route", "scripts/benchmark_route.py", True),
    ("offline_session", "scripts/test_offline_session.py", True),
    ("verify_portable", "scripts/verify_portable.py", False),
    ("demo_workflow_portable", "scripts/demo_workflow_portable.py", False),
    ("picocount_sandbox", "scripts/picocount_sandbox.py", False),
]

FULL_STEP = ("smoke_full", "scripts/smoke_full.py", True)


def _run_step(name: str, script: str) -> dict:
    path = os.path.join(ROOT, script)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [PY, path],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
        elapsed = round(time.perf_counter() - t0, 2)
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        tail = "\n".join(out.splitlines()[-8:]) if out else ""
        return {
            "step": name,
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "seconds": elapsed,
            "tail": tail,
        }
    except subprocess.TimeoutExpired:
        return {
            "step": name,
            "ok": False,
            "exit_code": -1,
            "seconds": round(time.perf_counter() - t0, 2),
            "tail": "TIMEOUT (>600s)",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "step": name,
            "ok": False,
            "exit_code": -1,
            "seconds": round(time.perf_counter() - t0, 2),
            "tail": str(exc),
        }


def _append_log(record: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(LOG_DIR, f"{day}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_cycle(*, full: bool = False) -> tuple[bool, dict]:
    from version import APP_VERSION

    steps = list(STEPS)
    if full:
        steps.append(FULL_STEP)

    results: list[dict] = []
    critical_fail = False
    print(f"Stress loop — {ROOT} v{APP_VERSION}\n")

    for name, script, critical in steps:
        print(f"  [{name}] ...", end=" ", flush=True)
        res = _run_step(name, script)
        results.append({**res, "critical": critical})
        mark = "PASS" if res["ok"] else ("WARN" if not critical else "FAIL")
        print(f"{mark} ({res['seconds']}s)")
        if not res["ok"] and critical:
            critical_fail = True
        if not res["ok"] and res.get("tail"):
            for line in res["tail"].splitlines()[-3:]:
                print(f"       {line}")

    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": APP_VERSION,
        "full": full,
        "critical_fail": critical_fail,
        "steps": results,
    }
    _append_log(record)

    print()
    if critical_fail:
        print("STRESS FAIL — critical step(s) failed. See logs/stress/")
        return False, record
    warns = [r for r in results if not r["ok"]]
    if warns:
        print(f"STRESS PASS with {len(warns)} optional warning(s).")
    else:
        print("STRESS PASS — all steps green.")
    return True, record


def main() -> int:
    ap = argparse.ArgumentParser(description="Traffic Deployer stress regression loop")
    ap.add_argument("--cycles", type=int, default=1, help="Repeat full cycle N times")
    ap.add_argument("--minutes", type=float, default=0, help="Run cycles until N minutes elapsed")
    ap.add_argument("--full", action="store_true", help="Include smoke_full (~3 min)")
    args = ap.parse_args()

    ok_all = True
    if args.minutes > 0:
        deadline = time.time() + args.minutes * 60.0
        cycle = 0
        print(f"Stress loop — run until {args.minutes:.0f} min ({'with' if args.full else 'without'} smoke_full)\n")
        while time.time() < deadline:
            cycle += 1
            left = max(0, int(deadline - time.time()))
            print(f"\n=== Cycle {cycle} (~{left // 60}m {left % 60}s left) ===")
            ok, _ = run_cycle(full=args.full)
            ok_all = ok_all and ok
        print(f"\nDone — {cycle} cycle(s) in {args.minutes:.0f} min window.")
        return 0 if ok_all else 1

    for i in range(args.cycles):
        if args.cycles > 1:
            print(f"\n=== Cycle {i + 1}/{args.cycles} ===")
        ok, _ = run_cycle(full=args.full)
        ok_all = ok_all and ok

    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
