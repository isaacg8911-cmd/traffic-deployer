"""Generate Volume by Lane CSV from .tvp or .pcbin (TrafficViewer layout).

Usage:
  .venv\\Scripts\\python.exe scripts\\volume_report.py path\\to\\study.pcbin
  .venv\\Scripts\\python.exe scripts\\volume_report.py path\\to\\study.tvp --out report.csv
  .venv\\Scripts\\python.exe scripts\\volume_report.py --all   # every stop with a download
"""
from __future__ import annotations

import argparse
import json
import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

from core.state import RouteState  # noqa: E402
from core import volume_report  # noqa: E402
from ui.paths import DATA_DIR  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Volume by Lane CSV (1029-style)")
    ap.add_argument("study", nargs="?", help=".tvp or .pcbin path")
    ap.add_argument("--out", "-o", default="", help="Output CSV path")
    ap.add_argument("--unit-id", default="", help="Report name / unit id")
    ap.add_argument("--dir1", default="", help="Primary direction label (e.g. East)")
    ap.add_argument("--dir2", default="", help="Secondary direction label (e.g. West)")
    ap.add_argument(
        "--all",
        action="store_true",
        help="Generate for all stops with counter_download_path in active profile",
    )
    args = ap.parse_args()

    if args.all:
        state = RouteState.load(DATA_DIR)
        results = volume_report.volume_reports_for_stops(state.stops, DATA_DIR)
        if not results:
            print("No counter downloads found on current route.")
            return 1
        ok = [r for r in results if r.get("ok")]
        fail = [r for r in results if not r.get("ok")]
        for r in ok:
            print(f"  OK  site {r.get('site_id')} → {r.get('path')} ({r.get('vehicle_count')} vehicles)")
        for r in fail:
            print(f"  FAIL site {r.get('site_id')}: {r.get('error')}")
        return 0 if ok and not fail else (1 if not ok else 0)

    if not args.study:
        ap.error("study path required unless --all")

    unit = args.unit_id or os.path.splitext(os.path.basename(args.study))[0]
    dest = args.out or volume_report.default_export_path(DATA_DIR, unit)
    res = volume_report.write_volume_csv(
        args.study,
        dest,
        stop=None,
        unit_id=unit,
        dir_primary=args.dir1,
        dir_secondary=args.dir2,
    )
    print(json.dumps({k: res.get(k) for k in (
        "ok", "error", "path", "vehicle_count", "directions", "started", "ended",
    )}, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
