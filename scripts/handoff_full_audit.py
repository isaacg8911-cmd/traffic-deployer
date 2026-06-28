"""Director handoff — run every gate in one report (source + portable + Isaac job files)."""
from __future__ import annotations

import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")

STEPS: tuple[tuple[str, bool], ...] = (
    ("quick_preflight.py", True),
    ("smoke_full.py", True),
    ("test_job_route_audit.py", True),
    ("test_field_sim.py", True),
    ("test_string_graph_coords.py", True),
    ("test_director_job.py", False),
    ("test_home_save.py", True),
    ("test_ui_wiring.py", True),
    ("verify_handoff_freshness.py", True),
    ("verify_frozen_bundle.py", True),
    ("verify_work_laptop_zip.py", True),
    ("verify_portable.py", True),
    ("audit_portable_scenarios.py", True),
    ("demo_workflow.py", True),
    ("demo_workflow_portable.py", True),
    ("test_offline_session.py", True),
    ("sandbox_audit.py", False),
)


def _run(script: str) -> tuple[bool, float, str]:
    t0 = time.time()
    proc = subprocess.run(
        [PY, os.path.join(ROOT, "scripts", script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    elapsed = time.time() - t0
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    tail = "\n".join(out.splitlines()[-6:]) if out else "(no output)"
    return proc.returncode == 0, elapsed, tail


def main() -> int:
    if not os.path.isfile(PY):
        print("FAIL: .venv missing — run START.bat")
        return 1

    print("TRAFFIC DEPLOYER — FULL HANDOFF AUDIT\n")
    results: list[tuple[str, bool, bool, float, str]] = []
    any_fail = False
    any_crit_fail = False

    for script, critical in STEPS:
        ok, secs, tail = _run(script)
        results.append((script, critical, ok, secs, tail))
        if not ok:
            any_fail = True
            if critical:
                any_crit_fail = True
        mark = "PASS" if ok else ("FAIL" if critical else "WARN")
        print(f"[{mark}] {script} ({secs:.1f}s)")

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    for script, critical, ok, secs, tail in results:
        tag = "CRIT" if critical else "opt "
        status = "OK  " if ok else "FAIL"
        print(f"  {status} [{tag}] {script} ({secs:.0f}s)")
        if not ok:
            for line in tail.splitlines():
                print(f"         {line}")

    print()
    if any_crit_fail:
        print("HANDOFF AUDIT FAIL — do not copy zip to work laptop")
        return 1
    if any_fail:
        print("HANDOFF AUDIT PASS with optional warnings — review above")
        return 0
    print("HANDOFF AUDIT PASS — all checks green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
