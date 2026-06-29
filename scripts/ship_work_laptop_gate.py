"""Hard gate before work-laptop zip ships. Runs portable audits in a loop."""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
LOOPS = 3


def _run(script: str) -> int:
    proc = subprocess.run([PY, os.path.join(ROOT, "scripts", script)], cwd=ROOT)
    return proc.returncode


def main() -> int:
    if not os.path.isfile(PY):
        print("FAIL: .venv missing — run START.bat")
        return 1

    scripts = (
        "verify_handoff_freshness.py",
        "verify_exe_build.py",
        "audit_portable_paths.py",
        "audit_portable_scenarios.py",
        "demo_workflow_portable.py",
        "test_portable_field_ready.py",
        "test_extracted_zip_field_ready.py",
        "test_string_graph_coords.py",
        "test_job_route_audit.py",
        "test_field_sim.py",
        "test_ui_wiring.py",
        "test_home_save.py",
    )
    for loop in range(1, LOOPS + 1):
        print(f"\n=== SHIP GATE pass {loop}/{LOOPS} ===")
        for name in scripts:
            print(f"\n--- {name} ---")
            rc = _run(name)
            if rc != 0:
                print(f"\nSHIP GATE FAIL on pass {loop}: {name} (exit {rc})")
                return rc

    print(f"\nSHIP GATE PASS — {LOOPS} loops clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
