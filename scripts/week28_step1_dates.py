"""Week 28 step 1 only: restamp TVP, volume CSV, and 60min CSV clocks.

Start 2026-09-22, end 2026-09-25, both TFC days. Keep clock times.
Drop hits and rows past that window (3-day count). Does not rename files,
does not touch photos, does not edit EST GPS.

Backs up originals to _week28_backup/ on first run.
"""
from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import week26_demand as w26
from week24_trim import parse_60min
from week28_common import (
    BACKUP_NAME,
    DAY1_END,
    DAY1_START,
    DAY2_END,
    DAY2_START,
    FOLDER,
    TFC_NAME,
    _cell_id,
    _sheet,
    load_tfc,
    resolve_count_site,
)

import openpyxl

w26.DAY1_START = DAY1_START
w26.DAY1_END = DAY1_END
w26.DAY2_START = DAY2_START
w26.DAY2_END = DAY2_END


def stamp_tfc_dates(tfc: Path) -> dict[str, int]:
    wb = openpyxl.load_workbook(tfc)
    out = {"day1": 0, "day2": 0}
    for day, want, key in (
        (1, DAY1_START, "day1"),
        (2, DAY2_START, "day2"),
    ):
        ws = _sheet(wb, "", day=day)
        stamped = datetime(want.year, want.month, want.day)
        for row in range(2, ws.max_row + 1):
            if not _cell_id(ws.cell(row, 2).value):
                continue
            if ws.cell(row, 1).value in (None, ""):
                continue
            cell = ws.cell(row, 1)
            cell.value = stamped
            cell.number_format = "M/D/YYYY"
            out[key] += 1
    wb.save(tfc)
    return out


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else FOLDER
    tfc = folder / TFC_NAME
    lines: list[str] = []

    def log(msg: str = "") -> None:
        print(msg)
        lines.append(msg)

    if not folder.is_dir():
        print(f"missing folder {folder}", file=sys.stderr)
        return 1
    if not tfc.is_file():
        print(f"missing TFC {tfc}", file=sys.stderr)
        return 1

    info = load_tfc(tfc)
    known = info["day1_installed"] | info["day2_installed"]
    backup = folder / BACKUP_NAME
    backup.mkdir(exist_ok=True)
    errors: list[str] = []
    n_ok = 0

    log("STEP 1 — dates only")
    log(f"Folder: {folder}")
    log(f"Window (Day 1 and Day 2): {DAY1_START} .. {DAY1_END}")
    log("Keep original clock times. Drop anything after the end date + original end clock.")
    log(f"Backup: {backup}")
    log()

    w26.backup_file(tfc, backup)
    try:
        counts = stamp_tfc_dates(tfc)
        log(f"TFC Day 1 date cells -> {DAY1_START}: {counts['day1']}")
        log(f"TFC Day 2 date cells -> {DAY2_START}: {counts['day2']}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"TFC dates: {exc}")
        log(f"FAIL TFC dates: {exc}")
        bak = backup / tfc.name
        if bak.exists():
            shutil.copy2(bak, tfc)
    log()

    log("=== 60min CSVs ===")
    for src in sorted(folder.glob("*.60min.csv")):
        if not src.is_file() or src.parent != folder:
            continue
        try:
            parsed = parse_60min(src)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{src.name}: {exc}")
            log(f"  FAIL {src.name}: {exc}")
            continue
        if not parsed["rows"]:
            log(f"  SKIP empty {src.name} (no count rows; left unchanged)")
            continue
        w26.backup_file(src, backup)
        try:
            n0 = len(lines)
            w26.process_60min(src, src, lines)
            for msg in lines[n0:]:
                print(msg)
            check = parse_60min(src)
            if check["start"].time() != parsed["start"].time():
                raise ValueError(
                    f"start clock changed {parsed['start'].time()} -> {check['start'].time()}"
                )
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{src.name}: {exc}")
            log(f"  FAIL {src.name}: {exc}")
            bak = backup / src.name
            if bak.exists():
                shutil.copy2(bak, src)
    log()

    log("=== volume CSVs ===")
    for src in sorted(folder.glob("*.csv")):
        if ".60min" in src.name.lower():
            continue
        site = resolve_count_site(src.name, known)
        if site not in known:
            errors.append(f"volume site not installed on TFC: {src.name}")
            log(f"  FAIL volume site not installed on TFC: {src.name}")
            continue
        w26.backup_file(src, backup)
        try:
            n0 = len(lines)
            w26.process_volume(src, src, lines)
            for msg in lines[n0:]:
                print(msg)
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{src.name}: {exc}")
            log(f"  FAIL {src.name}: {exc}")
            bak = backup / src.name
            if bak.exists():
                shutil.copy2(bak, src)
    log()

    log("=== TVP ===")
    for src in sorted(folder.glob("*.tvp")):
        site = resolve_count_site(src.name, known, src.read_bytes()[:500])
        if site not in known:
            errors.append(f"TVP site not installed on TFC: {src.name} -> {site}")
            log(f"  FAIL TVP site not installed on TFC: {src.name} -> {site}")
            continue
        if site in info["day1_installed"]:
            start_day, end_day = DAY1_START, DAY1_END
        else:
            start_day, end_day = DAY2_START, DAY2_END
        w26.backup_file(src, backup)
        try:
            n0 = len(lines)
            w26.process_tvp(src, src, start_day=start_day, end_day=end_day, lines=lines)
            for msg in lines[n0:]:
                print(msg)
            stem = src.name.split(".")[0]
            if not stem.lower().startswith(site):
                m = re.search(r"([nesw])c1b", src.name, re.I)
                direction = m.group(1).lower() if m else ""
                new_name = f"{site}{direction}c1b.tvp"
                dest = src.with_name(new_name)
                if dest.exists():
                    raise ValueError(f"cannot rename {src.name} -> {new_name}; dest exists")
                src.rename(dest)
                log(f"  renamed {stem}.tvp -> {new_name} (TFC site {site})")
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{src.name}: {exc}")
            log(f"  FAIL {src.name}: {exc}")
            bak = backup / src.name
            if bak.exists():
                shutil.copy2(bak, src)
    log()

    log("=== Step 1 summary ===")
    log(f"processed ok: {n_ok}")
    log(f"errors: {len(errors)}")
    for e in errors:
        log(f"  ERROR {e}")
    report = folder / "WEEK28_STEP1_DATES.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"Report: {report}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
