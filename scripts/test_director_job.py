"""Optional: run field sim on director's current job files (not required for ship gate).

Set before running:
  TD_JOB_XLS=c:\\path\\to\\sites.xls
  TD_JOB_EST=c:\\path\\Day1.est;c:\\path\\Day2.est
  TD_JOB_HOME_LAT=33.81  TD_JOB_HOME_LON=-117.92  (optional)
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")


def main() -> int:
    xls = os.environ.get("TD_JOB_XLS", "").strip()
    est = os.environ.get("TD_JOB_EST", "").strip()
    if not xls or not est:
        print("DIRECTOR JOB SKIP — set TD_JOB_XLS and TD_JOB_EST to test your current week files")
        print("  Ship gate uses bundled validation job files shipped with the app.")
        return 0

    print("Director job proof (optional, not ship blocker)\n")
    for script in ("test_job_route_audit.py", "test_field_sim.py"):
        print(f">>> {script}")
        proc = subprocess.run([PY, os.path.join(ROOT, "scripts", script)], cwd=ROOT)
        if proc.returncode != 0:
            return proc.returncode
    print("\nDIRECTOR JOB PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
