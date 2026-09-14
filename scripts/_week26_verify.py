"""Verify Week 26 restamp windows (read-only)."""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import openpyxl  # noqa: E402
from core import picocount_hits  # noqa: E402
from week24_trim import locate_stream, parse_60min, parse_volume_csv  # noqa: E402
from week26_demand import (  # noqa: E402
    DAY1_END,
    DAY1_START,
    DAY2_END,
    DAY2_START,
    load_tfc_sites,
    site_of,
)

FOLDER = Path(r"C:\Users\isaac\Downloads\week 26 ig\week 26 ig")
TFC = FOLDER / "Week 26 IG TFC.xlsx"


def main() -> int:
    errors: list[str] = []
    day1_sites, day2_sites, serial_to_tag = load_tfc_sites(TFC)

    wb = openpyxl.load_workbook(TFC, data_only=True)
    for sheet, expect in (("Week 26 Day 1 issac", DAY1_START), ("Week 26 Day 2  issac", DAY2_START)):
        ws = wb[sheet]
        for row in range(2, ws.max_row + 1):
            v = ws.cell(row, 1).value
            if v in (None, ""):
                continue
            if isinstance(v, datetime):
                d = v.date()
            elif isinstance(v, date):
                d = v
            else:
                d = date.fromisoformat(str(v)[:10])
            if d != expect:
                errors.append(f"TFC {sheet} row {row} date {d} != {expect}")

    csv60 = sorted(FOLDER.glob("*.60min.csv"))
    if len(csv60) != 15:
        errors.append(f"expected 15 60min files, got {len(csv60)}")
    for p in csv60:
        parsed = parse_60min(p)
        if parsed["start"].date() != DAY2_START:
            errors.append(f"{p.name} start {parsed['start']}")
        if parsed["end"].date() != DAY2_END:
            errors.append(f"{p.name} end {parsed['end']}")
        for ts, _ in parsed["rows"]:
            if ts.date() > DAY2_END or ts.date() < DAY2_START:
                errors.append(f"{p.name} row {ts} outside window")
                break
        if " " not in p.name:
            errors.append(f"{p.name} missing site prefix")
        tag = p.name.split(" ", 1)[0].lower()
        if tag[-1:] not in "nesw" or not tag[:-1].isdigit():
            errors.append(f"{p.name} bad prefix {tag!r}")

    for p in sorted(FOLDER.glob("*.csv")):
        if ".60min" in p.name:
            continue
        if site_of(p.name) not in day2_sites:
            continue
        parsed = parse_volume_csv(p)
        if parsed["started"].date() != DAY2_START:
            errors.append(f"{p.name} started {parsed['started']}")
        if parsed["ended"].date() != DAY2_END:
            errors.append(f"{p.name} ended {parsed['ended']}")
        days = [d["date"] for d in parsed["days"]]
        if any(d < DAY2_START or d > DAY2_END for d in days):
            errors.append(f"{p.name} days {days}")
        if date(2026, 9, 11) in days or date(2026, 9, 12) in days:
            errors.append(f"{p.name} still has Fri/Sat {days}")

    for p in sorted(FOLDER.glob("*.tvp")):
        site = site_of(p.name)
        if site in day1_sites:
            start_day, end_day = DAY1_START, DAY1_END
        elif site in day2_sites:
            start_day, end_day = DAY2_START, DAY2_END
        else:
            errors.append(f"{p.name} not on TFC")
            continue
        data = p.read_bytes()
        start = picocount_hits.decode_start_time_tvp(data)
        if start is None or start.date() != start_day:
            errors.append(f"{p.name} start {start} want {start_day}")
            continue
        _off, hits, _end = locate_stream(data)
        valid = [h for h in hits if 0 <= h["seconds"] <= 86400 * 8]
        last = start + timedelta(seconds=valid[-1]["seconds"])
        if last.date() > end_day:
            errors.append(f"{p.name} last {last} after {end_day}")
        if not data.startswith(b"TrafficViewerPro.Data"):
            errors.append(f"{p.name} magic missing")

    if errors:
        print("VERIFY FAIL")
        for e in errors:
            print(" ", e)
        return 1
    print("VERIFY OK")
    print(f"  60min={len(csv60)} volume day2 csvs prefixed TVP dates in window")
    print(f"  TFC day1={DAY1_START} day2={DAY2_START}")
    print(f"  serial map {len(serial_to_tag)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
