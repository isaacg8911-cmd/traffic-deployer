"""Verify Week 28 steps: dates, 60min names, photo size, EST vs TFC GPS."""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import picocount_hits  # noqa: E402
from core.est_viewer import pushpins_from_est  # noqa: E402
from week24_trim import locate_stream, parse_60min, parse_volume_csv  # noqa: E402
from week25_day2_rename_day1_shift import file_serial_key  # noqa: E402
from week26_photo_dates import read_datetime_original  # noqa: E402
from week27_est_gps import hav_m  # noqa: E402
from week28_step4_est_gps import stored_is_best_fit  # noqa: E402
from week28_common import (  # noqa: E402
    BACKUP_NAME,
    DAY1_END,
    DAY1_START,
    FOLDER,
    PHOTO_BACKUP,
    TFC_NAME,
    as_date,
    load_tfc,
    resolve_count_site,
)

LOW = 740 * 1024
HIGH = 860 * 1024
MAX_M = 25.0


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else FOLDER
    tfc = folder / TFC_NAME
    backup = folder / BACKUP_NAME
    errs: list[str] = []
    info = load_tfc(tfc)
    known = info["day1_installed"] | info["day2_installed"]

    wb_dates = []
    import openpyxl

    wb = openpyxl.load_workbook(tfc, data_only=True)
    for day, want in ((1, DAY1_START), (2, DAY1_START)):
        from week28_common import _sheet

        ws = _sheet(wb, "", day=day)
        for row in range(2, ws.max_row + 1):
            if ws.cell(row, 1).value in (None, ""):
                continue
            d = as_date(ws.cell(row, 1).value)
            wb_dates.append(d)
            if d != want:
                errs.append(f"TFC day {day} row {row} date {d} != {want}")
    print(f"TFC dated rows: {len(wb_dates)} unique {sorted(set(wb_dates))}")

    print("--- TVP ---")
    for src in sorted(folder.glob("*.tvp")):
        site = resolve_count_site(src.name, known, src.read_bytes()[:500])
        if site not in known:
            errs.append(f"TVP unresolved {src.name}")
            continue
        data = src.read_bytes()
        start = picocount_hits.decode_start_time_tvp(data)
        _off, hits, _end = locate_stream(data)
        valid = [h for h in hits if 0 <= h["seconds"] <= 86400 * 8]
        last = start + timedelta(seconds=valid[-1]["seconds"]) if start and valid else None
        bak = backup / src.name
        if not bak.is_file() and site == "5070":
            alt = backup / "50770nc1b.tvp"
            if alt.is_file():
                bak = alt
        if start is None or last is None:
            errs.append(f"{src.name}: no clock")
            continue
        if start.date() != DAY1_START:
            errs.append(f"{src.name}: start {start.date()} != {DAY1_START}")
        if last.date() > DAY1_END:
            errs.append(f"{src.name}: last {last} after {DAY1_END}")
        if last - start > timedelta(days=3, hours=1):
            errs.append(f"{src.name}: span {last - start} past 3 days")
        if bak.is_file():
            old = picocount_hits.decode_start_time_tvp(bak.read_bytes())
            if old and abs((datetime.combine(DAY1_START, old.time()) - start).total_seconds()) > 2:
                errs.append(f"{src.name}: clock not kept ({old.time()} vs {start.time()})")
        print(f"  {src.name}: {start} -> {last} hits={len(valid)} site={site}")

    print("--- volume ---")
    for src in sorted(folder.glob("*.csv")):
        if ".60min" in src.name.lower():
            continue
        parsed = parse_volume_csv(src)
        if parsed["started"].date() != DAY1_START:
            errs.append(f"{src.name}: started {parsed['started']}")
        if parsed["ended"].date() > DAY1_END:
            errs.append(f"{src.name}: ended {parsed['ended']}")
        days = [d["date"] for d in parsed["days"]]
        if any(d < DAY1_START or d > DAY1_END for d in days):
            errs.append(f"{src.name}: days {days}")
        if len(days) > 4:
            errs.append(f"{src.name}: {len(days)} calendar days")
        text = src.read_text(encoding="utf-8-sig")
        if not re.search(r"Started:,\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2} [AP]M", text):
            errs.append(f"{src.name}: start time format changed")
        print(f"  {src.name}: {parsed['started']} -> {parsed['ended']} days={days}")

    print("--- 60min ---")
    prefixed = 0
    for src in sorted(folder.glob("*.60min.csv")):
        parsed = parse_60min(src)
        if not parsed["rows"]:
            print(f"  empty left as {src.name}")
            continue
        if not re.match(r"^\d+[nesw] .+\.60min\.csv$", src.name, re.I):
            errs.append(f"60min name missing site+direction: {src.name}")
        else:
            prefixed += 1
        key = file_serial_key(src.name)
        tag = info["serial_to_tag"].get(key or -1)
        prefix = src.name.split(" ", 1)[0]
        if tag and prefix.lower() != tag.lower():
            errs.append(f"{src.name}: prefix {prefix} != TFC {tag}")
        if parsed["start"].date() != DAY1_START:
            errs.append(f"{src.name}: start {parsed['start']}")
        if parsed["end"].date() > DAY1_END:
            errs.append(f"{src.name}: end {parsed['end']}")
        bad = [ts for ts, _ in parsed["rows"] if ts.date() < DAY1_START or ts.date() > DAY1_END]
        if bad:
            errs.append(f"{src.name}: row outside window {bad[0]}")
        if parsed["rows"][-1][0] - parsed["rows"][0][0] > timedelta(days=3, hours=1):
            errs.append(f"{src.name}: row span past 3 days")
        # clock format stays HH:MM on data rows and Y-M-D H:M:S on study lines
        head = src.read_text(encoding="utf-8-sig").splitlines()[0]
        if not re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", head):
            errs.append(f"{src.name}: study start format changed")
        print(f"  {src.name}: {parsed['start']} -> {parsed['end']} rows={len(parsed['rows'])}")
    print(f"prefixed 60min: {prefixed}")

    print("--- photos ---")
    photo_backup = folder / PHOTO_BACKUP
    originals = sorted(photo_backup.glob("PXL_*.jpg"))
    current = sorted(
        p
        for p in folder.glob("*.jpg")
        if p.name[:1].isdigit()
    )
    print(f"  backup {len(originals)}  named {len(current)}")
    if len(originals) != len(current):
        errs.append(f"photo count backup {len(originals)} != named {len(current)}")
    for p in current:
        n = p.stat().st_size
        kb = n / 1024
        if not (LOW <= n <= HIGH):
            errs.append(f"{p.name}: {kb:.0f} KB not about 800")
        print(f"  {p.name}: {kb:.0f} KB taken {read_datetime_original(p)}")
    if originals:
        from week28_step3_photos import _assign

        assigned, assign_err = _assign(originals, info["order2"])
        errs.extend(assign_err)
        expect: dict[str, int] = {}
        for _src, sid, _dt in assigned:
            expect[sid] = expect.get(sid, 0) + 1
        got: dict[str, int] = {}
        for p in current:
            m = re.match(r"(\d+)", p.name)
            if not m:
                continue
            got[m.group(1)] = got.get(m.group(1), 0) + 1
        if got != expect:
            errs.append(f"photo sites {got} != first Day 2 sites {expect}")

    print("--- EST ---")
    for est in sorted(folder.glob("*.est")):
        pins = {p["site"]: p for p in pushpins_from_est(est)}
        for label, gps in (("Day 1", info["gps1"]), ("Day 2", info["gps2"])):
            hit = [s for s in gps if s in pins]
            if not hit:
                continue
            far = 0
            for sid in hit:
                lat, lon = gps[sid]
                d = hav_m(lat, lon, pins[sid]["lat"], pins[sid]["lon"])
                if d > MAX_M:
                    if stored_is_best_fit(est, sid, lat, lon):
                        print(f"    {sid} {d:.1f}m (best fit for EST digit width)")
                    else:
                        far += 1
                        errs.append(f"{est.name} {sid} {d:.1f}m from TFC")
            print(f"  {est.name} {label}: {len(hit)} pins, far={far}")

    print(f"errors: {len(errs)}")
    for e in errs:
        print(f"  ERROR {e}")
    report = folder / "WEEK28_VERIFY.txt"
    report.write_text("\n".join(errs) + ("\n" if errs else "ok\n"), encoding="utf-8")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
