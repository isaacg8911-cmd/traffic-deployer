"""Prove the ship gate's bug ledger blocks when it should (in a throwaway root)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS: list[str] = []


def check(cond: bool, name: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {name}")
    if not cond:
        FAILS.append(name)


def run(root: str, *args: str) -> int:
    return subprocess.run(
        [sys.executable, os.path.join(root, "scripts", "qa_ledger.py"), *args],
        cwd=root, capture_output=True, text=True,
    ).returncode


def write_ledger(root: str, bugs: list[dict]) -> None:
    with open(os.path.join(root, "qa", "bug_ledger.json"), "w", encoding="utf-8") as f:
        json.dump({"bugs": bugs}, f)


def main() -> int:
    root = tempfile.mkdtemp(prefix="tds_qa_")
    try:
        os.makedirs(os.path.join(root, "scripts"))
        os.makedirs(os.path.join(root, "core"))
        os.makedirs(os.path.join(root, "qa"))
        shutil.copy(os.path.join(HERE, "qa_ledger.py"), os.path.join(root, "scripts"))
        src = os.path.join(root, "core", "thing.py")
        with open(src, "w", encoding="utf-8") as f:
            f.write("x = 1\n")
        crit = {"id": "C-1", "rank": 1, "severity": "field-critical", "status": "open", "title": "bad"}
        major = {"id": "M-1", "rank": 2, "severity": "major", "status": "open", "title": "meh"}

        write_ledger(root, [major])
        check(run(root, "check") == 1, "blocks with no review on record")

        check(run(root, "record-review", "--since", "0.0.1", "--summary", "t") == 0, "record review")
        check(run(root, "check") == 0, "passes: review current, only major open")

        with open(src, "a", encoding="utf-8") as f:
            f.write("y = 2\n")
        check(run(root, "check") == 1, "blocks when code changed after review")
        run(root, "record-review", "--since", "0.0.1", "--summary", "t2")
        check(run(root, "check") == 0, "passes after re-review")

        write_ledger(root, [crit, major])
        check(run(root, "check") == 1, "blocks on open field-critical bug")

        write_ledger(root, [dict(crit, director_waiver="ship anyway 2026-09-25"), major])
        check(run(root, "check") == 0, "Director waiver unblocks")

        write_ledger(root, [dict(crit, status="fixed"), major])
        check(run(root, "check") == 0, "fixed critical no longer blocks")

        os.remove(os.path.join(root, "qa", "bug_ledger.json"))
        check(run(root, "check") == 1, "blocks when ledger file missing")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print(f"\n{'PASS' if not FAILS else 'FAIL'} test_qa_ledger ({len(FAILS)} failures)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
