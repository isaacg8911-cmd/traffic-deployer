"""MANDATORY gate before TrafficDeployer-WorkLaptop.zip ships. Exit 1 = do not copy to field."""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")

# Order matters: fast checks first, then field sim, then portable, then stress.
GATE_SCRIPTS = (
    "quick_preflight.py",
    "test_home_save.py",
    "test_ui_wiring.py",
    "test_job_route_audit.py",
    "test_field_sim.py",
    "test_manual_pick.py",
    "verify_handoff_freshness.py",
    "verify_frozen_bundle.py",
    "demo_workflow.py",
    "prove_user_paths.py",
    "smoke_full.py",
    "ship_work_laptop_gate.py",
    "verify_work_laptop_zip.py",
)


def main() -> int:
    if not os.path.isfile(PY):
        print("PRE-SHIP GATE FAIL: .venv missing — run START.bat")
        return 1

    print("=" * 60)
    print("PRE-SHIP GATE — mandatory before work-laptop zip")
    print("=" * 60)

    for name in GATE_SCRIPTS:
        print(f"\n>>> {name}")
        proc = subprocess.run(
            [PY, os.path.join(ROOT, "scripts", name)],
            cwd=ROOT,
        )
        if proc.returncode != 0:
            print(f"\nPRE-SHIP GATE FAIL on {name} (exit {proc.returncode})")
            print("Do NOT copy zip to work laptop. Fix and re-run BUILD_WORK_LAPTOP.bat")
            return proc.returncode

    print("\n" + "=" * 60)
    print("PRE-SHIP GATE PASS — safe to copy TrafficDeployer-WorkLaptop.zip")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
