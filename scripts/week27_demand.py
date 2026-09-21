"""Week 27 IG: restamp 3 days of real data onto Director timeline.

Day 1 (TFC Day 1 / hose TVPs): start 2026-09-14, end 2026-09-17.
Day 2 (TFC Day 2 / cam 60min + pulsar volume): start 2026-09-15, end 2026-09-18.
Keep original clock times. Drop rows/hits past the window.

Day 2 Apple pins (guides.htm) matched to TFC sites via Map 1.est; LAT/LON written.
60min CSVs: Traficam serial -> TFC '{site}{n|e} ' prefix.
Photos: Day 1 shots -> first Day 1 TFC sites; Day 2 shots -> first Day 2 TFC sites.

Default folder: C:\\Users\\isaac\\Downloads\\week 27\\week 27
Backs up data to _week27_backup/ and photos to _week27_photo_backup/.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote

APP = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(SCRIPTS))

import openpyxl  # noqa: E402
from core.est_viewer import pushpins_from_est  # noqa: E402
import week26_demand as w26  # noqa: E402
from week25_day2_rename_day1_shift import dest_name, file_serial_key  # noqa: E402
from week26_photo_dates import (  # noqa: E402
    list_photos,
    read_datetime_original,
    set_file_times,
    shift_jpeg_dates,
)

FOLDER = Path(r"C:\Users\isaac\Downloads\week 27\week 27")
GUIDES = Path(r"C:\Users\isaac\Downloads\guides.htm")
TFC_NAME = "Week 27 IG TFC.xlsx"
EST_DAY2 = "Week 27 Map 1.est"
BACKUP_NAME = "_week27_backup"
PHOTO_BACKUP = "_week27_photo_backup"

DAY1_START = date(2026, 9, 14)
DAY1_END = date(2026, 9, 17)
DAY2_START = date(2026, 9, 15)
DAY2_END = date(2026, 9, 18)

DAY1_SHEET = "Week 27 issac day 1"
DAY2_SHEET = "Week 27 issac day 2"

APPLE_MAX_M = 2500.0
APPLE_SOFT_M = 8000.0

w26.DAY1_START = DAY1_START
w26.DAY1_END = DAY1_END
w26.DAY2_START = DAY2_START
w26.DAY2_END = DAY2_END
w26.DAY1_SHEET = DAY1_SHEET
w26.DAY2_SHEET = DAY2_SHEET


def _cell_id(v) -> str:
    return w26._cell_id(v)


def _serial_key(v) -> int | None:
    return w26._serial_key(v)


def _sheet(wb, want: str, *, day: int):
    return w26._sheet(wb, want, day=day)


def hav_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def infer_dir(existing, notes: str) -> str:
    d = str(existing or "").strip().lower()[:1]
    if d in {"n", "e", "s", "w"}:
        return d
    blob = re.sub(r"\s+", "", str(notes or "").lower())
    if "s2n" in blob or "n2s" in blob:
        return "n"
    if "w2e" in blob or "e2w" in blob:
        return "e"
    return d


def serial_keys(v) -> set[int]:
    n = _serial_key(v)
    if n is None:
        return set()
    keys = {n}
    if n < 100000:
        keys.add(200000 + n)
    return keys


def extract_apple_places(path: Path) -> list[dict]:
    text = path.read_bytes().decode("utf-8", errors="replace")
    places: list[dict] = []
    for m in re.finditer(
        r'data-ref="ll\.(?P<lat>-?\d+\.\d+),(?P<lon>-?\d+\.\d+)"[^>]*>'
        r'.*?mw-collection-place-name[^>]*>(?P<name>[^<]+)<',
        text,
        re.S,
    ):
        places.append(
            {
                "lat": float(m.group("lat")),
                "lon": float(m.group("lon")),
                "name": unquote(m.group("name")).strip(),
            }
        )
    seen = set()
    ordered = []
    for p in places:
        key = (round(p["lat"], 5), round(p["lon"], 5))
        if key in seen:
            continue
        seen.add(key)
        ordered.append(p)
    return ordered


def match_apple_to_sites(
    places: list[dict], pin_map: dict[str, dict], installed: set[str]
) -> tuple[dict[str, dict], list[dict], list[str]]:
    candidates = [s for s in installed if s in pin_map]
    pairs: list[tuple[float, int, str]] = []
    for i, pl in enumerate(places):
        for sid in candidates:
            p = pin_map[sid]
            d = hav_m(pl["lat"], pl["lon"], p["lat"], p["lon"])
            pairs.append((d, i, sid))
    pairs.sort()
    used_pl: set[int] = set()
    used_site: set[str] = set()
    matches: dict[str, dict] = {}

    def take(limit: float) -> None:
        for d, i, sid in pairs:
            if i in used_pl or sid in used_site:
                continue
            if d > limit:
                continue
            used_pl.add(i)
            used_site.add(sid)
            matches[sid] = {
                "lat": places[i]["lat"],
                "lon": places[i]["lon"],
                "name": places[i]["name"],
                "dist_m": round(d, 1),
            }

    take(APPLE_MAX_M)
    take(APPLE_SOFT_M)
    unmatched_places = [places[i] for i in range(len(places)) if i not in used_pl]
    unmatched_sites = sorted(s for s in candidates if s not in used_site)
    return matches, unmatched_places, unmatched_sites


def load_tfc(tfc: Path) -> tuple[set[str], set[str], dict[int, str], dict[str, dict]]:
    """Day 1 sites, Day 2 installed, serial->tag, Day 2 row info."""
    wb = openpyxl.load_workbook(tfc, data_only=True)
    ws1 = _sheet(wb, DAY1_SHEET, day=1)
    ws2 = _sheet(wb, DAY2_SHEET, day=2)
    day1: set[str] = set()
    day2_installed: set[str] = set()
    day2_all: set[str] = set()
    serial_to_tag: dict[int, str] = {}
    rows: dict[str, dict] = {}
    missing_dir: list[str] = []

    for row in range(2, ws1.max_row + 1):
        site = _cell_id(ws1.cell(row, 2).value)
        if site:
            day1.add(site)

    for row in range(2, ws2.max_row + 1):
        site = _cell_id(ws2.cell(row, 2).value)
        if not site:
            continue
        serial = ws2.cell(row, 3).value
        notes = str(ws2.cell(row, 6).value or "")
        inst = str(ws2.cell(row, 7).value or "").strip().lower() in {"x", "1", "true", "yes"}
        dirc = infer_dir(ws2.cell(row, 4).value, notes)
        day2_all.add(site)
        rows[site] = {
            "row": row,
            "serial": serial,
            "dir": dirc,
            "notes": notes,
            "installed": inst,
        }
        if inst:
            day2_installed.add(site)
        if not inst or _serial_key(serial) is None:
            continue
        if dirc not in {"n", "e", "s", "w"}:
            missing_dir.append(f"site {site} serial {serial} dir={dirc!r}")
            continue
        tag = f"{site}{dirc}"
        for key in serial_keys(serial):
            if key in serial_to_tag and serial_to_tag[key] != tag:
                raise ValueError(
                    f"serial {key} maps to both {serial_to_tag[key]} and {tag}"
                )
            serial_to_tag[key] = tag
    if missing_dir:
        raise ValueError("Day 2 rows missing direction: " + "; ".join(missing_dir))
    overlap = day1 & day2_all
    if overlap:
        raise ValueError(f"site on both TFC days: {sorted(overlap)}")
    return day1, day2_installed | day2_all, serial_to_tag, rows


def stamp_tfc(
    tfc: Path,
    *,
    apple_by_site: dict[str, dict],
    est_pins: dict[str, dict],
    fill_dirs: bool,
) -> dict[str, int]:
    wb = openpyxl.load_workbook(tfc)
    ws1 = _sheet(wb, DAY1_SHEET, day=1)
    ws2 = _sheet(wb, DAY2_SHEET, day=2)
    n1 = n2 = n_dir = n_apple = n_est = 0
    d1 = datetime(DAY1_START.year, DAY1_START.month, DAY1_START.day)
    d2 = datetime(DAY2_START.year, DAY2_START.month, DAY2_START.day)
    for row in range(2, ws1.max_row + 1):
        if _cell_id(ws1.cell(row, 2).value):
            ws1.cell(row, 1).value = d1
            n1 += 1
    for row in range(2, ws2.max_row + 1):
        site = _cell_id(ws2.cell(row, 2).value)
        if not site:
            continue
        ws2.cell(row, 1).value = d2
        n2 += 1
        notes = str(ws2.cell(row, 6).value or "")
        if fill_dirs:
            new_dir = infer_dir(ws2.cell(row, 4).value, notes)
            old = str(ws2.cell(row, 4).value or "").strip().lower()[:1]
            if new_dir in {"n", "e", "s", "w"} and new_dir != old:
                ws2.cell(row, 4).value = new_dir
                n_dir += 1
        inst = str(ws2.cell(row, 7).value or "").strip().lower() in {"x", "1", "true", "yes"}
        if not inst:
            continue
        if site in apple_by_site:
            ws2.cell(row, 10).value = round(apple_by_site[site]["lat"], 6)
            ws2.cell(row, 11).value = round(apple_by_site[site]["lon"], 6)
            n_apple += 1
        elif site in est_pins and ws2.cell(row, 10).value in (None, ""):
            ws2.cell(row, 10).value = round(float(est_pins[site]["lat"]), 6)
            ws2.cell(row, 11).value = round(float(est_pins[site]["lon"]), 6)
            n_est += 1
    wb.save(tfc)
    return {"day1": n1, "day2": n2, "dirs": n_dir, "apple_gps": n_apple, "est_gps": n_est}


def beginning_sites(tfc: Path, sheet: str, day: int) -> list[tuple[str, str]]:
    """Installed sites in TFC order -> (site, dir)."""
    wb = openpyxl.load_workbook(tfc, data_only=True)
    ws = _sheet(wb, sheet, day=day)
    out: list[tuple[str, str]] = []
    for row in range(2, ws.max_row + 1):
        site = _cell_id(ws.cell(row, 2).value)
        inst = str(ws.cell(row, 7).value or "").strip().lower() in {"x", "1", "true", "yes"}
        skip = str(ws.cell(row, 8).value or "").strip().lower() in {"x", "1", "true", "yes"}
        if not site or not inst or skip:
            continue
        dirc = infer_dir(ws.cell(row, 4).value, str(ws.cell(row, 6).value or ""))
        out.append((site, dirc or ""))
    return out


def day1_beginning_sites(tfc: Path) -> list[tuple[str, str]]:
    return beginning_sites(tfc, DAY1_SHEET, 1)


def day2_beginning_sites(tfc: Path) -> list[tuple[str, str]]:
    return beginning_sites(tfc, DAY2_SHEET, 2)


def _assign_clock_order(
    photos: list[Path], sites: list[tuple[str, str]]
) -> tuple[list[tuple[Path, str]], list[str]]:
    errors: list[str] = []
    ordered = sorted(photos, key=lambda p: (read_datetime_original(p).time(), p.name))
    out: list[tuple[Path, str]] = []
    site_i = 0
    prev_dt: datetime | None = None
    current_site = ""
    for src in ordered:
        dt = read_datetime_original(src)
        if site_i >= len(sites):
            errors.append(f"more photos than beginning sites: {src.name}")
            continue
        if prev_dt is not None and abs((dt - prev_dt).total_seconds()) <= 30:
            sid = current_site
        else:
            sid = sites[site_i][0]
            site_i += 1
            current_site = sid
        prev_dt = dt
        out.append((src, sid))
    return out, errors


def _stamp_and_rename(
    src: Path,
    sid: str,
    backup: Path,
    stamp_day: date,
    used: dict[str, int],
    lines: list[str],
) -> str | None:
    dest_bak = backup / src.name
    if not dest_bak.exists():
        shutil.copy2(src, dest_bak)
    old_dt = read_datetime_original(src)
    new_dt = datetime.combine(stamp_day, old_dt.time())
    raw = src.read_bytes()
    patched, counts = shift_jpeg_dates(raw, old_dt, new_dt)
    if patched == raw and old_dt.date() != new_dt.date():
        return f"{src.name}: no date bytes patched"
    src.write_bytes(patched)
    set_file_times(src, new_dt)
    check = read_datetime_original(src)
    if check.date() != stamp_day or check.time() != old_dt.time():
        return f"{src.name}: Date Taken {check} want {new_dt}"
    used[sid] = used.get(sid, 0) + 1
    suffix = "" if used[sid] == 1 else f"-{used[sid]}"
    new_name = f"{sid}{suffix}.jpg"
    dest = src.with_name(new_name)
    if dest.exists() and dest.resolve() != src.resolve():
        tmp = src.with_name(f"_tmp_{sid}{suffix}.jpg")
        src.rename(tmp)
        src = tmp
        dest = src.with_name(new_name)
        if dest.exists() and dest.resolve() != src.resolve():
            return f"photo dest exists: {src.name} -> {new_name}"
    if dest != src:
        src.rename(dest)
    msg = (
        f"PHOTO {dest_bak.name} -> {new_name}: {old_dt} -> {check} "
        f"(exif={counts['exif_dt']} iso={counts['iso_date']})"
    )
    print(msg)
    lines.append(msg)
    return None


def rename_photos(
    folder: Path,
    backup: Path,
    day1_sites: list[tuple[str, str]],
    day2_sites: list[tuple[str, str]],
    lines: list[str],
    *,
    day2_names: set[str] | None = None,
) -> list[str]:
    """Name photos from first TFC sites. Day 1 suburban / Day 2 high-desert.

    Pixel GPS is stripped. Split: PXL_ filename date, or Director day2_names,
    or 5-digit Day 2 site names already applied.
    """
    errors: list[str] = []
    pxl = list_photos(folder)
    named = [
        p
        for p in sorted(folder.glob("*.jpg"))
        if p.name[:1].isdigit()
    ]
    if pxl:
        day1_photos, day2_photos = [], []
        for p in pxl:
            m = re.match(r"PXL_(\d{8})", p.name)
            raw_day = datetime.strptime(m.group(1), "%Y%m%d").date() if m else None
            if raw_day and raw_day >= date(2026, 9, 17):
                day2_photos.append(p)
            else:
                day1_photos.append(p)
    elif named:
        flagged = {n.lower() for n in (day2_names or set())}
        day1_photos, day2_photos = [], []
        for p in named:
            sid = re.match(r"(\d+)", p.name)
            site = sid.group(1) if sid else ""
            if p.name.lower() in flagged:
                day2_photos.append(p)
            elif len(site) >= 5:
                day2_photos.append(p)
            else:
                day1_photos.append(p)
    else:
        return ["no photos to rename"]

    a1, e1 = _assign_clock_order(day1_photos, day1_sites)
    a2, e2 = _assign_clock_order(day2_photos, day2_sites)
    errors.extend(e1)
    errors.extend(e2)

    used: dict[str, int] = {}
    # Day 2 first so Day 1 can take 4977.jpg after the desert shot is moved.
    pending = [(src, sid, DAY2_START) for src, sid in a2] + [
        (src, sid, DAY1_START) for src, sid in a1
    ]
    # Two-pass: rename everyone to temps, then to final names.
    temps: list[tuple[Path, str, date]] = []
    for src, sid, stamp in pending:
        tmp = src.with_name(f"_w27_{src.stem}.jpg")
        n = 0
        while tmp.exists():
            n += 1
            tmp = src.with_name(f"_w27_{src.stem}_{n}.jpg")
        if tmp != src:
            src.rename(tmp)
        temps.append((tmp, sid, stamp))
    for src, sid, stamp in temps:
        err = _stamp_and_rename(src, sid, backup, stamp, used, lines)
        if err:
            errors.append(err)
    return errors


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else FOLDER
    tfc = Path(sys.argv[2]) if len(sys.argv) > 2 else folder / TFC_NAME
    guides = Path(sys.argv[3]) if len(sys.argv) > 3 else GUIDES
    report_path = folder / "WEEK27_REPORT.txt"
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
    if not guides.is_file():
        print(f"missing guides {guides}", file=sys.stderr)
        return 1

    day1_sites, day2_sites, serial_to_tag, day2_rows = load_tfc(tfc)
    backup = folder / BACKUP_NAME
    backup.mkdir(exist_ok=True)
    photo_backup = folder / PHOTO_BACKUP
    photo_backup.mkdir(exist_ok=True)

    log(f"Folder: {folder}")
    log(f"TFC: {tfc}")
    log(f"Guides: {guides}")
    log(f"Backup: {backup}")
    log(f"Day 1 window: {DAY1_START} .. {DAY1_END} (keep times, 3-day count)")
    log(f"Day 2 window: {DAY2_START} .. {DAY2_END} (keep times, 3-day count)")
    log(
        f"TFC Day 1 sites: {len(day1_sites)}  Day 2 sites: {len(day2_sites)}  "
        f"Day 2 serial tags: {len(serial_to_tag)}"
    )
    log()

    errors: list[str] = []
    n_ok = 0

    # --- Apple Day 2 pins -> TFC ---
    places = extract_apple_places(guides)
    est_path = folder / EST_DAY2
    pin_map = {p["site"]: p for p in pushpins_from_est(est_path)} if est_path.is_file() else {}
    installed = {s for s, r in day2_rows.items() if r["installed"]}
    apple_by_site, leftover_places, leftover_sites = match_apple_to_sites(
        places, pin_map, installed
    )
    log("=== Day 2 guides.htm -> TFC sites ===")
    log(f"Apple pins: {len(places)}  matched: {len(apple_by_site)}")
    for sid in sorted(apple_by_site, key=lambda s: (len(s), s)):
        m = apple_by_site[sid]
        log(
            f"  site {sid} {m['lat']:.6f},{m['lon']:.6f}  {m['name']}  "
            f"(EST {m['dist_m']}m)"
        )
    if leftover_places:
        log("Apple pins with no site:")
        for p in leftover_places:
            log(f"  {p['lat']:.6f},{p['lon']:.6f} {p['name']}")
    if leftover_sites:
        log("Installed Day 2 with no Apple pin (EST fallback GPS):")
        for s in leftover_sites:
            log(f"  site {s}")
    (folder / "_week27_apple_matches.json").write_text(
        json.dumps(
            {
                "matches": apple_by_site,
                "unmatched_places": leftover_places,
                "unmatched_sites": leftover_sites,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    log()

    w26.backup_file(tfc, backup)
    tfc_counts = stamp_tfc(
        tfc, apple_by_site=apple_by_site, est_pins=pin_map, fill_dirs=True
    )
    # reload tags after direction fill
    day1_sites, day2_sites, serial_to_tag, day2_rows = load_tfc(tfc)
    log("=== TFC dates + Day 2 GPS/dir ===")
    log(f"  Day 1 Date cells -> {DAY1_START}: {tfc_counts['day1']}")
    log(f"  Day 2 Date cells -> {DAY2_START}: {tfc_counts['day2']}")
    log(f"  Directions filled from cam notes: {tfc_counts['dirs']}")
    log(f"  LAT/LON from guides.htm: {tfc_counts['apple_gps']}")
    log(f"  LAT/LON from Map 1.est fallback: {tfc_counts['est_gps']}")
    log()

    log("=== Day 2 60min CSVs ===")
    csv60 = sorted(folder.glob("*.60min.csv"))
    if not csv60:
        errors.append("no *.60min.csv files")
        log("  FAIL no *.60min.csv files")
    for src in csv60:
        w26.backup_file(src, backup)
        try:
            n0 = len(lines)
            w26.process_60min(src, src, lines)
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

    log("=== Day 2 volume CSVs ===")
    vol_files = [
        p
        for p in sorted(folder.glob("*.csv"))
        if ".60min" not in p.name.lower() and w26.site_of(p.name) in day2_sites
    ]
    if not vol_files:
        errors.append("no Day 2 volume CSVs")
        log("  FAIL no Day 2 volume CSVs")
    for src in vol_files:
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

    log("=== TVP date shift + trim ===")
    tvps = sorted(folder.glob("*.tvp"))
    if not tvps:
        errors.append("no TVP files")
        log("  FAIL no TVP files")
    for src in tvps:
        site = w26.site_of(src.name)
        if site in day1_sites:
            start_day, end_day = DAY1_START, DAY1_END
        elif site in day2_sites:
            start_day, end_day = DAY2_START, DAY2_END
        else:
            errors.append(f"TVP site not on TFC: {src.name}")
            log(f"  FAIL TVP site not on TFC: {src.name}")
            continue
        w26.backup_file(src, backup)
        try:
            n0 = len(lines)
            w26.process_tvp(src, src, start_day=start_day, end_day=end_day, lines=lines)
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

    log("=== Day 2 60min rename (serial -> site+dir) ===")
    renamed, skipped, rename_err = w26.rename_60min(folder, serial_to_tag)
    for a, b in renamed:
        log(f"  {a} -> {b}")
    for n in skipped:
        log(f"  already: {n}")
    for e in rename_err:
        errors.append(e)
        log(f"  FAIL {e}")
    used_keys = {file_serial_key(b) or file_serial_key(a) for a, b in renamed}
    used_keys |= {file_serial_key(n) for n in skipped}
    cam3_missing: list[str] = []
    for site, rec in day2_rows.items():
        notes = rec["notes"].lower()
        keys = serial_keys(rec["serial"])
        if not keys or "cam" not in notes:
            continue
        if keys.isdisjoint(used_keys):
            cam3_missing.append(f"  site {site} serial {rec['serial']}")
    if cam3_missing:
        log("TFC cam3 serials with no 60min CSV:")
        for c in cam3_missing:
            log(c)
    log(f"renamed={len(renamed)} already={len(skipped)} errors={len(rename_err)}")
    log()

    log("=== Photos -> first sites (Day 1 and Day 2) ===")
    begin1 = day1_beginning_sites(tfc)
    begin2 = day2_beginning_sites(tfc)
    log("Day 1 beginning: " + ", ".join(s for s, _ in begin1[:8]))
    log("Day 2 beginning: " + ", ".join(s for s, _ in begin2[:8]))
    photo_err = rename_photos(
        folder, photo_backup, begin1, begin2, lines, day2_names={"4977.jpg", "4941.jpg"}
    )
    for e in photo_err:
        errors.append(e)
        log(f"  FAIL {e}")
    log()

    log("=== Summary ===")
    log(f"processed ok: {n_ok}")
    log(f"errors: {len(errors)}")
    if errors:
        for e in errors:
            log(f"  ERROR {e}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"Report: {report_path}")
    if errors:
        return 1
    if not renamed and not skipped:
        print("no 60min CSVs renamed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
