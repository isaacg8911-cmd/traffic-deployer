"""Week 28 step 2 only: prefix 60min CSV names with site and direction.

Example: 001712-128.60min.csv -> '5125n 001712-128.60min.csv'
Does not change count dates. Does not touch TVP, volume CSV, photos, or EST.
"""
from __future__ import annotations

import sys
from pathlib import Path

from week24_trim import parse_60min
from week25_day2_rename_day1_shift import dest_name
from week26_demand import backup_file
from week28_common import BACKUP_NAME, FOLDER, TFC_NAME, load_tfc


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else FOLDER
    tfc = folder / TFC_NAME
    lines: list[str] = []

    def log(msg: str = "") -> None:
        print(msg)
        lines.append(msg)

    if not folder.is_dir() or not tfc.is_file():
        print(f"missing folder or TFC under {folder}", file=sys.stderr)
        return 1

    info = load_tfc(tfc)
    serial_to_tag = info["serial_to_tag"]
    backup = folder / BACKUP_NAME
    backup.mkdir(exist_ok=True)
    errors: list[str] = []

    log("STEP 2 — 60min filenames only")
    log(f"Folder: {folder}")
    log("Prefix: {site}{direction} + space + original name")
    log()

    skipped_empty: list[str] = []
    real: list[Path] = []
    for src in sorted(folder.glob("*.60min.csv")):
        parsed = parse_60min(src)
        if not parsed["rows"]:
            skipped_empty.append(src.name)
            log(f"  SKIP empty (not renamed): {src.name}")
            continue
        real.append(src)
        backup_file(src, backup)

    renamed: list[tuple[str, str]] = []
    skipped: list[str] = []
    for src in real:
        new_name = dest_name(src.name, serial_to_tag)
        if new_name is None:
            errors.append(f"no TFC match: {src.name}")
            log(f"  FAIL no TFC match: {src.name}")
            continue
        if new_name == src.name:
            skipped.append(src.name)
            log(f"  already: {src.name}")
            continue
        dest = src.with_name(new_name)
        if dest.exists():
            errors.append(f"dest exists: {src.name} -> {new_name}")
            log(f"  FAIL dest exists: {src.name} -> {new_name}")
            continue
        src.rename(dest)
        renamed.append((src.name, new_name))
        log(f"  {src.name} -> {new_name}")

    log()
    log(f"renamed={len(renamed)} already={len(skipped)} empty={len(skipped_empty)} errors={len(errors)}")
    for e in errors:
        log(f"  ERROR {e}")
    report = folder / "WEEK28_STEP2_RENAME.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"Report: {report}")
    if errors:
        return 1
    if not renamed and not skipped:
        print("no 60min CSVs renamed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
