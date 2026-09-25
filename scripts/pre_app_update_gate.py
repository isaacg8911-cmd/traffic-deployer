"""Mandatory gate before TrafficDeployer-AppUpdate folder ships (creator laptop only).

Trials the same routing paths field laptops hit — including networkx/string graphml —
without requiring the full 1.6 GB work-laptop zip rebuild.

Blocks first on qa/bug_ledger.json: the pre-ship review must cover the current
source and no field-critical bug may be open (see scripts/qa_ledger.py).
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
EXE = os.path.join(ROOT, "dist", "TrafficDeployer", "TrafficDeployer.exe")
HANDOFF = os.path.join(ROOT, "dist", "TrafficDeployer-AppUpdate", "TrafficDeployer")
HANDOFF_EXE = os.path.join(HANDOFF, "TrafficDeployer.exe")

GATE_SCRIPTS = (
    "smoke_full.py",
    "test_grab_gps_safe.py",
    "test_install_commit.py",
    "test_update_overwrite.py",
    "test_shipment.py",
)


def _handoff_fresh() -> list[str]:
    fails: list[str] = []
    if not os.path.isfile(EXE):
        fails.append("TrafficDeployer.exe missing — run BUILD_APP_UPDATE.bat")
        return fails
    if not os.path.isfile(HANDOFF_EXE):
        fails.append("TrafficDeployer-AppUpdate folder missing — run pack_app_update.py")
        return fails
    if not os.path.isdir(os.path.join(HANDOFF, "_internal")):
        fails.append("AppUpdate _internal missing — re-run BUILD_APP_UPDATE.bat")
    if not os.path.isdir(os.path.join(HANDOFF, "web")):
        fails.append("AppUpdate web missing — re-run BUILD_APP_UPDATE.bat")
    if os.path.getmtime(HANDOFF_EXE) < os.path.getmtime(EXE) - 1.0:
        fails.append("AppUpdate folder older than exe — re-run BUILD_APP_UPDATE.bat")
    elif not fails:
        total_mb = sum(
            os.path.getsize(os.path.join(r, f))
            for r, _, files in os.walk(HANDOFF)
            for f in files
        ) / (1024 * 1024)
        print(f"  OK  AppUpdate folder fresh ({total_mb:.0f} MB, no zip)")
    return fails


def main() -> int:
    if not os.path.isfile(PY):
        print("APP UPDATE GATE FAIL: .venv missing — run START.bat")
        return 1

    print("=" * 60)
    print("APP UPDATE GATE — creator laptop trial before field send")
    print("=" * 60)

    print("\n>>> qa_ledger.py check")
    ledger = subprocess.run([PY, os.path.join(ROOT, "scripts", "qa_ledger.py"), "check"], cwd=ROOT)
    if ledger.returncode != 0:
        print("\nAPP UPDATE GATE FAIL: review stale or field-critical bug open")
        print("Do NOT copy AppUpdate folder to field laptops.")
        return ledger.returncode

    handoff_fails = _handoff_fresh()
    if handoff_fails:
        for f in handoff_fails:
            print(f"  FAIL {f}")
        return 1

    for name in GATE_SCRIPTS:
        print(f"\n>>> {name}")
        proc = subprocess.run([PY, os.path.join(ROOT, "scripts", name)], cwd=ROOT)
        if proc.returncode != 0:
            print(f"\nAPP UPDATE GATE FAIL on {name} (exit {proc.returncode})")
            print("Do NOT copy AppUpdate folder to field laptops.")
            return proc.returncode

    print("\n" + "=" * 60)
    print("APP UPDATE GATE PASS — safe to copy TrafficDeployer-AppUpdate folder")
    print("=" * 60)
    subprocess.run([PY, os.path.join(ROOT, "scripts", "qa_ledger.py"), "report"], cwd=ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
