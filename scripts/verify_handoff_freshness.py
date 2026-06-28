"""Fail handoff if frozen exe/zip is older than critical source fixes."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "dist", "TrafficDeployer", "TrafficDeployer.exe")
ZIP_PATH = os.path.join(ROOT, "dist", "TrafficDeployer-WorkLaptop.zip")

# Source files that must be baked into the work-laptop bundle before ship.
CRITICAL_SOURCES = (
    "main.py",
    "road_router.py",
    "core/routing.py",
    "web/app.js",
    "ui/route_pick_dialog.py",
    "ui/threads.py",
    "ui/web_page.py",
    "core/state.py",
    "core/setup_checklist.py",
    "core/offline_gate.py",
    "ui/pages/setup_page.py",
    "ui/pages/route_page.py",
    "version.py",
)

# Strings that must exist in source (regression guards for field UX).
SOURCE_MARKERS = (
    ("ui/route_pick_dialog.py", "apply_requested"),
    ("ui/threads.py", "RouteApplyPickThread"),
    ("ui/threads.py", "pick_sides"),
    ("main.py", "RouteApplyPickThread"),
    ("main.py", "_enter_pick_map_focus"),
    ("main.py", "_parse_stop_click"),
    ("main.py", "_commit_home_start"),
    ("web/app.js", "alreadyPicked"),
    ("web/app.js", "pick_waiting"),
    ("core/routing.py", "pick_cross_locked"),
    ("core/state.py", "set_start_point"),
    ("core/setup_checklist.py", "Tap Apply route"),
)


def _mtime(path: str) -> float:
    return os.path.getmtime(path) if os.path.isfile(path) else 0.0


def main() -> int:
    fails: list[str] = []
    warns: list[str] = []

    for rel, marker in SOURCE_MARKERS:
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.isfile(path):
            fails.append(f"missing source {rel}")
            continue
        text = open(path, encoding="utf-8").read()
        if marker not in text:
            fails.append(f"{rel} missing marker {marker!r}")

    if not os.path.isfile(EXE):
        fails.append("dist/TrafficDeployer/TrafficDeployer.exe missing — run BUILD_WORK_LAPTOP.bat")
    else:
        exe_t = _mtime(EXE)
        stale: list[str] = []
        for rel in CRITICAL_SOURCES:
            src = os.path.join(ROOT, rel.replace("/", os.sep))
            if not os.path.isfile(src):
                continue
            if _mtime(src) > exe_t + 1.0:
                stale.append(rel)
        if stale:
            fails.append(
                "frozen exe is STALE — rebuild required before USB handoff: "
                + ", ".join(stale)
            )
        else:
            print(f"  OK  exe fresh vs critical sources ({EXE})")

    if not os.path.isfile(ZIP_PATH):
        warns.append("TrafficDeployer-WorkLaptop.zip missing — run pack after build")
    else:
        zip_t = _mtime(ZIP_PATH)
        if os.path.isfile(EXE) and zip_t < _mtime(EXE) - 1.0:
            fails.append("zip older than exe — re-run pack_work_laptop_dist.py")
        elif os.path.isfile(EXE) and _mtime(EXE) > zip_t + 1.0:
            fails.append("zip older than exe — re-run pack_work_laptop_dist.py")
        else:
            mb = os.path.getsize(ZIP_PATH) / (1024 * 1024)
            print(f"  OK  zip ({mb:.0f} MB)")

    print()
    for w in warns:
        print(f"  WARN {w}")
    if fails:
        print(f"HANDOFF FRESHNESS FAIL ({len(fails)})")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("HANDOFF FRESHNESS PASS — bundle matches current source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
