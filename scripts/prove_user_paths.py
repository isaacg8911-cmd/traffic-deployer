"""Run all user-simulation proofs (real Qt app + map) — run before ship.

Prefer: scripts/app_check.py --tier user  (writes audit to logs/app_check/)
"""
from __future__ import annotations

import subprocess
import sys

ROOT = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))


def main() -> int:
    py = __import__("os").path.join(ROOT, ".venv", "Scripts", "python.exe")
    if not __import__("os").path.isfile(py):
        py = sys.executable
    proc = subprocess.run(
        [py, __import__("os").path.join(ROOT, "scripts", "app_check.py"), "--tier", "user"],
        cwd=ROOT,
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
