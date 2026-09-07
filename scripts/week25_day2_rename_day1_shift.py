"""Week 25 IG: rename Day 2 Cam3 60min CSVs; shift Day 1 TVP clocks -2 days.

Day 2: match Traficam serial in filename to TFC Day 2 rows; prefix
  '{site}{n|e} {original}.60min.csv' (space, per Director).

Day 1: all *.tvp — patch PicoCount start/end clocks and Excel end serials
  two calendar days earlier (hit stream unchanged, no trim).

Default folder: C:\\Users\\isaac\\Downloads\\week 25 ig\\week 25 ig
Writes WEEK25_REPORT.txt in that folder. Backs up TVPs to _tvp_backup_pre_shift/.
"""
from __future__ import annotations

import shutil
import struct
import sys
from datetime import datetime, timedelta
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import openpyxl  # noqa: E402
from core import picocount_hits  # noqa: E402
from week24_trim import (  # noqa: E402
    EXCEL_BASE,
    MAGIC,
    excel_serials,
    locate_stream,
    pack_pc,
    pc_clocks,
)

FOLDER = Path(r"C:\Users\isaac\Downloads\week 25 ig\week 25 ig")
TFC_NAME = "Week 25 IG TFC.xlsx"
DAY2_SHEET = "Week 25 Day 2 issac"
SHIFT_DAYS = 2


def _cell_id(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def _serial_key(v) -> int | None:
    s = _cell_id(v)
    if not s or not s.isdigit():
        return None
    return int(s)


def load_day2_serial_to_tag(tfc: Path) -> dict[int, str]:
    """serial_int -> '{site}{n|e}' from Day 2 installed rows with a serial."""
    wb = openpyxl.load_workbook(tfc, data_only=True)
    if DAY2_SHEET not in wb.sheetnames:
        raise ValueError(f"missing sheet {DAY2_SHEET!r}; have {wb.sheetnames}")
    ws = wb[DAY2_SHEET]
    mapping: dict[int, str] = {}
    missing_dir: list[str] = []
    for row in range(2, ws.max_row + 1):
        site = _cell_id(ws.cell(row, 2).value)
        serial = _serial_key(ws.cell(row, 3).value)
        dirc = str(ws.cell(row, 4).value or "").strip().lower()[:1]
        if not site or serial is None:
            continue
        if dirc not in {"n", "e", "s", "w"}:
            missing_dir.append(f"site {site} serial {serial} dir={dirc!r}")
            continue
        tag = f"{site}{dirc}"
        if serial in mapping and mapping[serial] != tag:
            raise ValueError(
                f"serial {serial} maps to both {mapping[serial]} and {tag}"
            )
        mapping[serial] = tag
    if missing_dir:
        raise ValueError("Day 2 rows missing direction: " + "; ".join(missing_dir))
    return mapping


def file_serial_key(name: str) -> int | None:
    """Serial from 001712-120.60min.csv or already-prefixed names."""
    stem = name
    if stem.lower().endswith(".csv"):
        stem = stem[:-4]
    if stem.lower().endswith(".60min"):
        stem = stem[: -len(".60min")]
    # strip optional '{site}{dir} ' or '{site}{dir}-' prefix
    if " " in stem:
        stem = stem.split(" ", 1)[-1]
    m_first = stem.split("-", 1)[0]
    if m_first.isdigit() and len(m_first) >= 4:
        return int(m_first)
    return None


def dest_name(name: str, serial_to_tag: dict[int, str]) -> str | None:
    key = file_serial_key(name)
    if key is None:
        return None
    tag = serial_to_tag.get(key)
    if not tag:
        return None
    # peel existing site prefix if re-run
    rest = name
    if " " in name:
        left, right = name.split(" ", 1)
        if left[:-1].isdigit() and left[-1:].lower() in "nesw":
            rest = right
    prefix = f"{tag} "
    if rest.startswith(prefix):
        return rest
    return prefix + rest


def rename_day2_csvs(
    folder: Path, serial_to_tag: dict[int, str]
) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    renamed: list[tuple[str, str]] = []
    skipped: list[str] = []
    errors: list[str] = []
    for src in sorted(folder.glob("*.60min.csv")):
        new_name = dest_name(src.name, serial_to_tag)
        if new_name is None:
            errors.append(f"no TFC match: {src.name}")
            continue
        if new_name == src.name:
            skipped.append(src.name)
            continue
        dest = src.with_name(new_name)
        if dest.exists():
            errors.append(f"dest exists: {src.name} -> {new_name}")
            continue
        src.rename(dest)
        renamed.append((src.name, new_name))
    return renamed, skipped, errors


def shift_tvp_clocks(path: Path, *, days: int = SHIFT_DAYS) -> dict:
    """Shift start/end metadata clocks earlier by `days`; keep full hit stream."""
    orig = path.read_bytes()
    if not orig.startswith(MAGIC):
        raise ValueError(f"{path.name}: missing TrafficViewerPro.Data magic")
    orig_start = picocount_hits.decode_start_time_tvp(orig)
    if orig_start is None:
        raise ValueError(f"{path.name}: no study start")

    stream_off, hits, _stream_end = locate_stream(orig)
    valid = [h for h in hits if 0 <= h["seconds"] <= 86400 * 8]
    if not valid:
        raise ValueError(f"{path.name}: no valid hits")
    orig_last = orig_start + timedelta(seconds=valid[-1]["seconds"])
    delta = timedelta(days=days)
    new_start = orig_start - delta
    new_last = orig_last - delta

    data = bytearray(orig)
    start_patches = 0
    end_patches = 0
    for o, dt, raw in pc_clocks(orig):
        if o >= stream_off:
            continue
        if abs((dt - orig_start).total_seconds()) < 2:
            data[o : o + 8] = pack_pc(raw, new_start)
            start_patches += 1
        else:
            # treat other pre-stream clocks as end / download-ish
            data[o : o + 8] = pack_pc(raw, dt - delta)
            end_patches += 1

    excel_patches = 0
    for o, d, dt in excel_serials(orig):
        if o >= stream_off:
            continue
        new_serial = ((dt - delta) - EXCEL_BASE).total_seconds() / 86400.0
        struct.pack_into("<d", data, o, new_serial)
        excel_patches += 1

    path.write_bytes(bytes(data))
    verify = picocount_hits.decode_start_time_tvp(bytes(data))
    if verify is None or abs((verify - new_start).total_seconds()) > 2:
        raise ValueError(f"{path.name}: verify start {verify} != {new_start}")

    return {
        "orig_start": orig_start,
        "new_start": new_start,
        "orig_last": orig_last,
        "new_last": new_last,
        "hits": len(valid),
        "start_patches": start_patches,
        "end_patches": end_patches,
        "excel_patches": excel_patches,
        "bytes": len(data),
    }


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else FOLDER
    tfc = Path(sys.argv[2]) if len(sys.argv) > 2 else folder / TFC_NAME
    report_path = folder / "WEEK25_REPORT.txt"
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

    log(f"Folder: {folder}")
    log(f"TFC: {tfc}")
    log(f"Shift: -{SHIFT_DAYS} calendar days on Day 1 TVP clocks")
    log()

    # --- Day 2 rename ---
    mapping = load_day2_serial_to_tag(tfc)
    log(f"=== Day 2 Cam3 rename ({len(mapping)} TFC serials) ===")
    renamed, skipped, errors = rename_day2_csvs(folder, mapping)
    for a, b in renamed:
        log(f"  {a} -> {b}")
    for n in skipped:
        log(f"  already: {n}")
    for e in errors:
        log(f"  FAIL {e}")
    log(f"renamed={len(renamed)} already={len(skipped)} errors={len(errors)}")

    used_keys = {file_serial_key(b) or file_serial_key(a) for a, b in renamed}
    used_keys |= {file_serial_key(n) for n in skipped}
    cam_notes = []
    wb = openpyxl.load_workbook(tfc, data_only=True)
    ws = wb[DAY2_SHEET]
    for row in range(2, ws.max_row + 1):
        notes = str(ws.cell(row, 6).value or "").lower()
        serial = _serial_key(ws.cell(row, 3).value)
        site = _cell_id(ws.cell(row, 2).value)
        if serial is None:
            continue
        if "cam" in notes and serial not in used_keys:
            cam_notes.append(f"  site {site} serial {serial} (cam note, no 60min file)")
    if cam_notes:
        log("TFC cam rows with no 60min CSV:")
        for c in cam_notes:
            log(c)
    log()

    # --- Day 1 TVP shift ---
    backup = folder / "_tvp_backup_pre_shift"
    backup.mkdir(exist_ok=True)
    tvps = sorted(folder.glob("*.tvp"))
    log(f"=== Day 1 TVP date shift ({len(tvps)} files, -{SHIFT_DAYS} days) ===")
    tvp_ok: list[dict] = []
    tvp_fail: list[str] = []
    for src in tvps:
        bak = backup / src.name
        if not bak.exists():
            shutil.copy2(src, bak)
        try:
            info = shift_tvp_clocks(src, days=SHIFT_DAYS)
            tvp_ok.append({"file": src.name, **info})
            log(
                f"  {src.name}: start {info['orig_start']} -> {info['new_start']}; "
                f"last {info['orig_last']} -> {info['new_last']}; "
                f"hits={info['hits']} "
                f"patches start={info['start_patches']} end={info['end_patches']} "
                f"excel={info['excel_patches']}"
            )
        except Exception as exc:  # noqa: BLE001 — report all failures
            tvp_fail.append(f"{src.name}: {exc}")
            log(f"  FAIL {src.name}: {exc}")
            # restore from backup if we corrupted
            if bak.exists():
                shutil.copy2(bak, src)

    log()
    log("=== Summary ===")
    log(f"Day 2 CSV renamed: {len(renamed)} / {len(renamed) + len(skipped) + len(errors)}")
    log(f"Day 1 TVP shifted: {len(tvp_ok)} / {len(tvps)}")
    log(f"TVP backup: {backup}")
    if errors or tvp_fail:
        log(f"ERRORS: csv={len(errors)} tvp={len(tvp_fail)}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"Report written: {report_path}")

    if errors or tvp_fail:
        return 1
    if not renamed and not skipped:
        print("no Day 2 60min CSVs renamed", file=sys.stderr)
        return 1
    if not tvp_ok:
        print("no Day 1 TVPs shifted", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
