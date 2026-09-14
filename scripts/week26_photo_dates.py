"""Shift Week 26 IG JPEG Date Taken back 2 calendar days.

Keeps clock times. Patches EXIF + XMP date strings in place (no recompress).
Backs up originals to _week26_photo_backup/.

Default folder: C:\\Users\\isaac\\Downloads\\week 26 ig\\week 26 ig
"""
from __future__ import annotations

import os
import re
import shutil
import struct
import sys
from datetime import datetime, timedelta
from pathlib import Path

FOLDER = Path(r"C:\Users\isaac\Downloads\week 26 ig\week 26 ig")
BACKUP_NAME = "_week26_photo_backup"
SHIFT_DAYS = 2

EXIF_DT = re.compile(rb"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})")


def _u16(buf: bytes, off: int, le: bool) -> int:
    return struct.unpack_from("<H" if le else ">H", buf, off)[0]


def _u32(buf: bytes, off: int, le: bool) -> int:
    return struct.unpack_from("<I" if le else ">I", buf, off)[0]


def _ifd_entries(tiff: bytes, ifd_off: int, le: bool) -> dict[int, tuple[int, int, int]]:
    n = _u16(tiff, ifd_off, le)
    out = {}
    for i in range(n):
        e = ifd_off + 2 + i * 12
        tag = _u16(tiff, e, le)
        typ = _u16(tiff, e + 2, le)
        count = _u32(tiff, e + 4, le)
        val_off = e + 8
        unit = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}.get(typ, 1)
        size = unit * count
        data_off = val_off if size <= 4 else _u32(tiff, val_off, le)
        out[tag] = (typ, count, data_off)
    return out


def _ascii(tiff: bytes, count: int, off: int) -> str:
    raw = tiff[off : off + count]
    return raw.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()


def read_datetime_original(path: Path) -> datetime:
    data = path.read_bytes()
    if data[:2] != b"\xff\xd8":
        raise ValueError(f"{path.name}: not JPEG")
    i = 2
    app1 = None
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        if marker == 0xDA:
            break
        seglen = struct.unpack_from(">H", data, i + 2)[0]
        payload = data[i + 4 : i + 2 + seglen]
        if marker == 0xE1 and payload.startswith(b"Exif\x00\x00"):
            app1 = payload[6:]
            break
        i += 2 + seglen
    if app1 is None:
        raise ValueError(f"{path.name}: no EXIF")
    le = app1[:2] == b"II"
    ifd0 = _u32(app1, 4, le)
    entries0 = _ifd_entries(app1, ifd0, le)
    if 0x8769 not in entries0:
        raise ValueError(f"{path.name}: no Exif IFD")
    typ, count, off = entries0[0x8769]
    exif_off = _u32(app1, off, le) if typ == 4 and count == 1 else off
    exif_e = _ifd_entries(app1, exif_off, le)
    if 0x9003 not in exif_e:
        raise ValueError(f"{path.name}: no DateTimeOriginal")
    typ, count, off = exif_e[0x9003]
    text = _ascii(app1, count, off)
    return datetime.strptime(text, "%Y:%m:%d %H:%M:%S")


def _shift_match_exif(m: re.Match[bytes], old_date: datetime.date, new_date) -> bytes:
    dt = datetime(
        int(m.group(1)),
        int(m.group(2)),
        int(m.group(3)),
        int(m.group(4)),
        int(m.group(5)),
        int(m.group(6)),
    )
    if dt.date() != old_date:
        return m.group(0)
    shifted = datetime.combine(new_date, dt.time())
    return shifted.strftime("%Y:%m:%d %H:%M:%S").encode("ascii")


def shift_jpeg_dates(data: bytes, old_dt: datetime, new_dt: datetime) -> tuple[bytes, dict[str, int]]:
    old_date = old_dt.date()
    new_date = new_dt.date()
    counts = {"exif_dt": 0, "iso_date": 0, "compact": 0}

    def exif_sub(m: re.Match[bytes]) -> bytes:
        out = _shift_match_exif(m, old_date, new_date)
        if out != m.group(0):
            counts["exif_dt"] += 1
        return out

    data = EXIF_DT.sub(exif_sub, data)

    old_iso = old_date.strftime("%Y-%m-%d").encode("ascii")
    new_iso = new_date.strftime("%Y-%m-%d").encode("ascii")
    n_iso = data.count(old_iso)
    if n_iso:
        data = data.replace(old_iso, new_iso)
        counts["iso_date"] = n_iso

    old_c = old_date.strftime("%Y%m%d").encode("ascii")
    new_c = new_date.strftime("%Y%m%d").encode("ascii")
    n_c = data.count(old_c)
    if n_c:
        data = data.replace(old_c, new_c)
        counts["compact"] = n_c

    return data, counts


def set_file_times(path: Path, dt: datetime) -> None:
    ts = dt.timestamp()
    os.utime(path, (ts, ts))
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        FILE_WRITE_ATTRIBUTES = 0x0100
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        OPEN_EXISTING = 3
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        # 100-ns since 1601-01-01 UTC
        unix_100ns = int(dt.timestamp() * 10_000_000)
        ft_int = unix_100ns + 116444736000000000
        ft = FILETIME(ft_int & 0xFFFFFFFF, ft_int >> 32)
        CreateFileW = ctypes.windll.kernel32.CreateFileW
        CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        CreateFileW.restype = wintypes.HANDLE
        handle = CreateFileW(
            str(path),
            FILE_WRITE_ATTRIBUTES,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        if handle == wintypes.HANDLE(-1).value:
            return
        ctypes.windll.kernel32.SetFileTime(handle, ctypes.byref(ft), None, ctypes.byref(ft))
        ctypes.windll.kernel32.CloseHandle(handle)


def list_photos(folder: Path) -> list[Path]:
    photos = []
    seen = set()
    for p in sorted(folder.glob("*.jpg")) + sorted(folder.glob("*.JPG")) + sorted(folder.glob("*.jpeg")):
        if p.name.startswith("PXL_") and p.name not in seen:
            seen.add(p.name)
            photos.append(p)
    return photos


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else FOLDER
    if not folder.is_dir():
        print(f"missing folder {folder}", file=sys.stderr)
        return 1

    photos = list_photos(folder)
    if not photos:
        print(f"no PXL_*.jpg in {folder}", file=sys.stderr)
        return 1

    backup = folder / BACKUP_NAME
    backup.mkdir(exist_ok=True)
    shift = timedelta(days=SHIFT_DAYS)
    print(f"Folder: {folder}")
    print(f"Backup: {backup}")
    print(f"Shift: -{SHIFT_DAYS} days (keep clock)")
    print()

    for src in photos:
        dest_bak = backup / src.name
        if not dest_bak.exists():
            shutil.copy2(src, dest_bak)
        old_dt = read_datetime_original(src)
        new_dt = old_dt - shift
        raw = src.read_bytes()
        patched, counts = shift_jpeg_dates(raw, old_dt, new_dt)
        if patched == raw:
            print(f"FAIL {src.name}: no date bytes patched", file=sys.stderr)
            return 1
        src.write_bytes(patched)
        set_file_times(src, new_dt)
        check = read_datetime_original(src)
        if check != new_dt:
            print(f"FAIL {src.name}: DateTimeOriginal {check} want {new_dt}", file=sys.stderr)
            return 1
        if check.date() != old_dt.date() - shift:
            print(f"FAIL {src.name}: date not -{SHIFT_DAYS}d", file=sys.stderr)
            return 1
        if check.time() != old_dt.time():
            print(f"FAIL {src.name}: clock changed {old_dt.time()} -> {check.time()}", file=sys.stderr)
            return 1
        print(
            f"{src.name}: {old_dt} -> {check}  "
            f"(exif={counts['exif_dt']} iso={counts['iso_date']} compact={counts['compact']})"
        )

    print()
    print(f"OK {len(photos)} photos Date Taken -{SHIFT_DAYS} days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
