"""Batch pickup Google Maps link pages per map/day from a TDS_Report export.

Install order = ExactTime on each sheet (oldest install first for pickup).

Usage:
  set TD_REPORT_XLS=c:\\path\\to\\TDS_Report_DEFAULT_2026-06-17.xlsx
  python scripts/batch_pickup_links.py

Optional:
  TD_REPORT_OUT=c:\\path\\to\\folder   (default: tds_data/exports beside repo)
  TD_REPORT_PROFILE=DEFAULT            (filename prefix)
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "tds_data")
REPORT = os.environ.get(
    "TD_REPORT_XLS",
    r"C:\Users\isaac\Downloads\TDS_Report_DEFAULT_2026-06-17.xlsx",
)
OUT_DIR = os.environ.get("TD_REPORT_OUT", "").strip() or os.path.dirname(REPORT)
PROFILE = os.environ.get("TD_REPORT_PROFILE", "DEFAULT").strip() or "DEFAULT"

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  OK  {name}")
    else:
        msg = name + (f": {detail}" if detail else "")
        print(f"  FAIL {msg}")
        FAILURES.append(msg)


def main() -> int:
    print(f"Batch pickup links — {ROOT}\n")
    from core import export, maps_links

    check("report file", os.path.isfile(REPORT), REPORT)
    if FAILURES:
        return 1

    sheets = export.parse_report_workbook(REPORT)
    check("report sheets", bool(sheets), "no day sheets found")
    if FAILURES:
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    written: list[str] = []
    for sheet, stops in sorted(sheets.items()):
        installed = [s for s in stops if s.get("installed")]
        if not installed:
            print(f"  SKIP {sheet} — no installed sites")
            continue
        from core.state import ca_now
        day, _ = ca_now()
        safe_sheet = re.sub(r"[^\w\-]+", "_", sheet.strip())[:40] or "DAY"
        safe_prof = re.sub(r"[^\w\-]+", "_", PROFILE.strip())[:24] or "DEFAULT"
        path = os.path.join(
            OUT_DIR,
            f"TDS_Route_Links_{safe_prof}_{safe_sheet}_Pickup_{day}.html",
        )
        count, errors = maps_links.write_pickup_links_page(
            stops, path, profile=PROFILE, sheet=sheet,
        )
        check(f"{sheet} pickup links", count >= 1, f"{count} links")
        if errors:
            for e in errors:
                print(f"    warn: {e}")
        written.append(path)
        print(f"       -> {path}")

    check("at least one day batched", bool(written))
    if FAILURES:
        print(f"\nBATCH PICKUP FAIL — {len(FAILURES)} check(s)")
        return 1
    print(f"\nBATCH PICKUP PASS — {len(written)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
