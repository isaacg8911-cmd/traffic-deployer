"""Build shift handoff with clean filenames (IG TFC + Map 1/2 .est).

Usage:
  python scripts/build_shift_handoff.py

Environment overrides:
  TD_HANDOFF_REPORT   TDS_Report / IG TFC .xlsx (optional — uses live backup if set)
  TD_HANDOFF_EST_D1   Day 1 source .est
  TD_HANDOFF_EST_D2   Day 2 source .est
  TD_HANDOFF_OUT      Output folder (default: tds_data/exports/shift_handoff)
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA_DIR = os.path.join(ROOT, "tds_data")
REPORT = os.environ.get("TD_HANDOFF_REPORT", "")
EST_D1 = os.environ.get(
    "TD_HANDOFF_EST_D1",
    r"c:\Users\isaac\Downloads\Week 14 Day 1 Isaac (1).est",
)
EST_D2 = os.environ.get(
    "TD_HANDOFF_EST_D2",
    r"c:\Users\isaac\Downloads\Week 14 Day 2 Isaac (1).est",
)
OUT = os.environ.get(
    "TD_HANDOFF_OUT",
    os.path.join(DATA_DIR, "exports", "shift_handoff"),
)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  OK  {name}" + (f" — {detail}" if detail else ""))
    else:
        msg = name + (f": {detail}" if detail else "")
        print(f"  FAIL {msg}")
        FAILURES.append(msg)


def _load_shift() -> tuple[list[dict], list[str], str]:
    """Stops, est_paths, ig_tfc_path from encrypted backup."""
    import persistence

    backup = os.path.join(DATA_DIR, "tds_backup_DEFAULT.json")
    data = persistence.load_state(backup, DATA_DIR) if os.path.isfile(backup) else {}
    stops = list(data.get("stops") or [])
    est_paths = [p for p in (data.get("est_paths") or []) if p]
    ig = str(data.get("ig_tfc_path") or "")
    return stops, est_paths, ig


def _latest_export_xlsx() -> str:
    folder = os.path.join(DATA_DIR, "exports")
    if not os.path.isdir(folder):
        return ""
    candidates = [
        os.path.join(folder, n)
        for n in os.listdir(folder)
        if n.lower().endswith(".xlsx") and "ig_tfc" in n.lower()
    ]
    if not candidates:
        candidates = [
            os.path.join(folder, n)
            for n in os.listdir(folder)
            if n.lower().endswith(".xlsx")
        ]
    if not candidates:
        return ""
    return max(candidates, key=os.path.getmtime)


def _stops_from_report(path: str) -> list[dict]:
    from core import export

    sheets = export.parse_report_workbook(path)
    stops: list[dict] = []
    for sheet_stops in sheets.values():
        stops.extend(sheet_stops)
    return stops


def main() -> int:
    print(f"Shift handoff builder — {ROOT}\n")
    from core import handoff

    est_paths = [p for p in (EST_D1, EST_D2) if p]
    for est in est_paths:
        check(f"EST {os.path.basename(est)}", os.path.isfile(est), est)

    stops, saved_ests, ig_from_shift = _load_shift()
    if saved_ests and not os.environ.get("TD_HANDOFF_EST_D1"):
        est_paths = [p for p in saved_ests if os.path.isfile(p)] or est_paths

    ig_tfc = REPORT or ig_from_shift
    if REPORT and os.path.isfile(REPORT):
        check("report override", True, REPORT)
        if not stops:
            stops = _stops_from_report(REPORT)
    elif stops:
        check("shift backup", True, f"{len(stops)} stops")
    elif _latest_export_xlsx():
        report = _latest_export_xlsx()
        check("latest export", True, report)
        stops = _stops_from_report(report)
        if not ig_tfc:
            ig_tfc = report
    else:
        check("stops source", False, "Run app shift or set TD_HANDOFF_REPORT")
    if FAILURES:
        return 1

    ig_candidates = [
        REPORT,
        os.environ.get("TD_WEEK14_IG_TFC", ""),
        os.path.join(DATA_DIR, "week_14_ig_tfc.xlsx"),
        r"c:\Users\isaac\Downloads\week 14 ig tfc.xlsx",
    ]
    if not ig_tfc:
        for c in ig_candidates:
            if c and os.path.isfile(c):
                ig_tfc = c
                break

    result = handoff.export_shift_handoff(
        stops,
        est_paths,
        data_dir=DATA_DIR,
        ig_tfc_path=ig_tfc,
        out_dir=OUT,
    )
    for w in result.get("warnings") or []:
        print(f"  WARN {w}")
    for er in result.get("est_results") or []:
        print(
            f"  OK  {os.path.basename(er.get('output', '?'))} — "
            f"{er.get('sites_patched', 0)}/{er.get('sites_requested', 0)} sites, "
            f"{er.get('pins_patched', 0)} pins ({er.get('format', '?')})",
        )
    for key in ("excel", "map1", "map2", "readme"):
        path = (result.get("files") or {}).get(key)
        if path:
            check(os.path.basename(path), os.path.isfile(path), path)

    print(f"\nShift handoff folder:\n  {result['folder']}\n")
    if not result.get("ok") or FAILURES:
        print(f"SHIFT HANDOFF FAIL — {len(FAILURES) + len(result.get('errors') or [])} issue(s)")
        for e in result.get("errors") or []:
            print(f"  {e}")
        return 1
    print("SHIFT HANDOFF PASS — zip the shift_handoff folder and send")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
