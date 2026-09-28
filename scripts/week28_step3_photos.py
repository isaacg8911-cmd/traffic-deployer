"""Week 28 step 3 only: Day 2 photos.

Pictures are Day 2, assigned from the first installed Day 2 sites in TFC
order (shots within 30 seconds stay on the same site). Each JPEG is
recompressed to about 800 KB. Date Taken is Tuesday 2026-09-22
at the original clock time.

Does not edit TVP, CSV, TFC, or EST.
Backs up originals to _week28_photo_backup/.
"""
from __future__ import annotations

import io
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from week26_photo_dates import (
    list_photos,
    read_datetime_original,
    set_file_times,
    shift_jpeg_dates,
)
from week28_common import DAY2_START, FOLDER, PHOTO_BACKUP, TFC_NAME, load_tfc

TARGET = 800 * 1024
LOW = 740 * 1024
HIGH = 860 * 1024


def _assign(photos: list[Path], sites: list[tuple[str, str]]) -> tuple[list[tuple[Path, str, datetime]], list[str]]:
    errors: list[str] = []
    ordered = sorted(photos, key=lambda p: (read_datetime_original(p).time(), p.name))
    out: list[tuple[Path, str, datetime]] = []
    site_i = 0
    prev: datetime | None = None
    current = ""
    for src in ordered:
        dt = read_datetime_original(src)
        if site_i >= len(sites):
            errors.append(f"more photos than Day 2 sites: {src.name}")
            continue
        if prev is not None and abs((dt - prev).total_seconds()) <= 30:
            sid = current
        else:
            sid = sites[site_i][0]
            site_i += 1
            current = sid
        prev = dt
        out.append((src, sid, dt))
    return out, errors


def _jpeg(im: Image.Image, quality: int, exif: bytes) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True, exif=exif)
    return buf.getvalue()


def compress_about_800kb(im: Image.Image, exif: bytes) -> bytes:
    """Pick a size and quality whose file lands near 800 KB."""
    work = im
    long_edge = max(work.size)
    if long_edge > 2560:
        scale = 2560 / long_edge
        work = work.resize(
            (max(1, int(work.width * scale)), max(1, int(work.height * scale))),
            Image.Resampling.LANCZOS,
        )
    best: bytes | None = None
    for _ in range(7):
        chosen: bytes | None = None
        chosen_delta = 10**18
        for quality in range(50, 93, 2):
            data = _jpeg(work, quality, exif)
            delta = abs(len(data) - TARGET)
            if delta < chosen_delta:
                chosen_delta = delta
                chosen = data
            if LOW <= len(data) <= HIGH:
                return data
        if chosen is None:
            raise ValueError("jpeg encode failed")
        best = chosen
        if len(best) > HIGH:
            w, h = work.size
            work = work.resize(
                (max(1, int(w * 0.88)), max(1, int(h * 0.88))),
                Image.Resampling.LANCZOS,
            )
            continue
        if len(best) < LOW and (work.size != im.size):
            w = min(im.width, int(work.width / 0.88))
            h = min(im.height, int(work.height / 0.88))
            if (w, h) == work.size:
                return best
            work = im.resize((w, h), Image.Resampling.LANCZOS)
            continue
        return best
    if best is None:
        raise ValueError("jpeg encode failed")
    return best


def restamp_tuesday(folder: Path) -> int:
    """Set Date Taken on the named site JPEGs to Tuesday, same clock."""
    tuesday = DAY2_START
    if tuesday.weekday() != 1:
        print(f"{tuesday} is not a Tuesday", file=sys.stderr)
        return 1
    photos = sorted(p for p in folder.glob("*.jpg") if p.name[:1].isdigit())
    if not photos:
        print(f"no named photos in {folder}", file=sys.stderr)
        return 1
    print(f"Date Taken -> {tuesday} (Tuesday), keep clock")
    errors: list[str] = []
    for src in photos:
        old = read_datetime_original(src)
        new_dt = datetime.combine(tuesday, old.time())
        if old == new_dt:
            print(f"  already {src.name}: {old}")
            continue
        raw = src.read_bytes()
        patched, counts = shift_jpeg_dates(raw, old, new_dt)
        if counts["exif_dt"] < 1:
            errors.append(f"{src.name}: Date Taken bytes not found")
            print(f"  FAIL {src.name}: Date Taken bytes not found")
            continue
        src.write_bytes(patched)
        set_file_times(src, new_dt)
        check = read_datetime_original(src)
        if check != new_dt:
            errors.append(f"{src.name}: {check} want {new_dt}")
            print(f"  FAIL {src.name}: {check} want {new_dt}")
            continue
        print(f"  {src.name}: {old} -> {check}  ({src.stat().st_size/1024:.0f} KB)")
    return 1 if errors else 0


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

    photos = list_photos(folder)
    if not photos:
        print("no PXL_ photos to assign", file=sys.stderr)
        return 1

    info = load_tfc(tfc)
    sites = info["order2"]
    assigned, errors = _assign(photos, sites)
    backup = folder / PHOTO_BACKUP
    backup.mkdir(exist_ok=True)

    log("STEP 3 — Day 2 photos only")
    log(f"Folder: {folder}")
    log(f"Day 2 first sites: {', '.join(s for s, _ in sites[:12])}")
    log(f"Photos: {len(photos)}  clusters assigned: {len(assigned)}")
    log("Date Taken kept. File size target about 800 KB.")
    log()

    used: dict[str, int] = {}
    staged: list[tuple[Path, str, datetime, bytes]] = []
    for src, sid, dt in assigned:
        dest_bak = backup / src.name
        if not dest_bak.exists():
            shutil.copy2(src, dest_bak)
        im = Image.open(src)
        im = ImageOps.exif_transpose(im)
        if im.mode != "RGB":
            im = im.convert("RGB")
        exif = im.getexif()
        exif[0x0112] = 1
        taken = datetime.combine(DAY2_START, dt.time())
        stamp = taken.strftime("%Y:%m:%d %H:%M:%S")
        exif[0x0132] = stamp
        sub = exif.get_ifd(0x8769)
        sub[0x9003] = stamp
        sub[0x9004] = stamp
        try:
            data = compress_about_800kb(im, exif.tobytes())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{src.name}: {exc}")
            log(f"  FAIL {src.name}: {exc}")
            continue
        staged.append((src, sid, dt, data))

    if errors:
        for e in errors:
            log(f"  ERROR {e}")
        report = folder / "WEEK28_STEP3_PHOTOS.txt"
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    temps: list[tuple[Path, str, datetime, bytes]] = []
    for src, sid, dt, data in staged:
        tmp = src.with_name(f"_w28_{src.stem}.jpg")
        n = 0
        while tmp.exists():
            n += 1
            tmp = src.with_name(f"_w28_{src.stem}_{n}.jpg")
        src.rename(tmp)
        temps.append((tmp, sid, dt, data))

    for src, sid, dt, data in temps:
        src.write_bytes(data)
        taken = datetime.combine(DAY2_START, dt.time())
        set_file_times(src, taken)
        check = read_datetime_original(src)
        if check.time() != dt.time() or check.date() != DAY2_START:
            errors.append(f"{src.name}: Date Taken {check} want {taken}")
            continue
        size = src.stat().st_size
        if not (LOW <= size <= HIGH):
            errors.append(f"{src.name}: {size} bytes, want about 800 KB")
        used[sid] = used.get(sid, 0) + 1
        suffix = "" if used[sid] == 1 else f"-{used[sid]}"
        new_name = f"{sid}{suffix}.jpg"
        dest = src.with_name(new_name)
        if dest.exists() and dest.resolve() != src.resolve():
            errors.append(f"photo dest exists: {new_name}")
            continue
        if dest != src:
            src.rename(dest)
        log(f"  {backup.name}/{src.name.removeprefix('_w28_')} -> {new_name}: {size/1024:.0f} KB  taken {check}")

    log()
    log(f"errors: {len(errors)}")
    for e in errors:
        log(f"  ERROR {e}")
    report = folder / "WEEK28_STEP3_PHOTOS.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"Report: {report}")
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--tuesday":
        target = Path(sys.argv[2]) if len(sys.argv) > 2 else FOLDER
        raise SystemExit(restamp_tuesday(target))
    raise SystemExit(main())
