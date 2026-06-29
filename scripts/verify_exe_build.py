"""Verify PyInstaller output before work-laptop zip (required gate)."""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "dist", "TrafficDeployer", "TrafficDeployer.exe")
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")


def main() -> int:
    fails: list[str] = []
    if os.path.isfile(EXE):
        mb = os.path.getsize(EXE) / (1024 * 1024)
        print(f"  OK  work-laptop exe ({mb:.1f} MB)")
    else:
        fails.append(f"missing {EXE}")
        print("  FAIL work-laptop exe — run scripts/build_exe.ps1")

    web_in_dist = os.path.join(ROOT, "dist", "TrafficDeployer", "_internal", "web", "app.js")
    if os.path.isfile(web_in_dist):
        print("  OK  web assets in _internal/web")
    else:
        fails.append("web bundle")
        print("  FAIL web assets not found in dist/_internal/web")

    proc = subprocess.run(
        [PY, os.path.join(ROOT, "scripts", "audit_portable_paths.py")],
        cwd=ROOT,
    )
    if proc.returncode != 0:
        fails.append("audit_portable_paths")
    else:
        print("  OK  audit_portable_paths")

    for label, script in (
        ("demo_workflow (source)", "demo_workflow.py"),
        ("demo_workflow (frozen exe)", "demo_workflow_portable.py"),
    ):
        proc2 = subprocess.run(
            [PY, os.path.join(ROOT, "scripts", script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if proc2.returncode == 0:
            print(f"  OK  {label}")
        else:
            fails.append(script)
            print(f"  FAIL {label}")
            tail = ((proc2.stdout or "") + (proc2.stderr or "")).strip()
            if tail:
                for line in tail.splitlines()[-4:]:
                    print(f"       {line}")

    if fails:
        print(f"\nEXE BUILD VERIFY FAIL ({len(fails)})")
        return 1
    print("\nEXE BUILD VERIFY PASS — safe for work-laptop zip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
