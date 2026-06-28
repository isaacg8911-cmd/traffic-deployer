"""Apply field install GPS from TDS_Report onto Streets & Trips .EST pushpins.

Week 14+ files store lat/lon as fixed-width ASCII inside each pushpin record.
Week 13-style files use a UserData coordinate table indexed by *x pushpin names.
"""
from __future__ import annotations

import re
import struct
from pathlib import Path

from core import export

_LAT_TAG = b"\x14\x08"
_LON_TAG = b"\x15\t"
_INLINE_LAT = re.compile(rb"\x14\x08([0-9.\-]+)")
_INLINE_LON = re.compile(rb"\x15\t([0-9.\-]+)")
_SITE_ID = re.compile(r"^\d{3,5}$")


def _fmt_lat(v: float) -> bytes:
    for prec in (5, 4, 6, 3, 2):
        s = f"{v:.{prec}f}"
        if len(s) <= 8:
            return s.ljust(8, "0")[:8].encode("ascii")
    return f"{v:.4f}"[:8].encode("ascii")


def _fmt_lon(v: float) -> bytes:
    for prec in (4, 3, 5, 2, 1):
        s = f"{v:.{prec}f}"
        if len(s) <= 9:
            return s.ljust(9, "0")[:9].encode("ascii")
    return f"{v:.3f}"[:9].encode("ascii")


def detect_est_format(data: bytes) -> str:
    """Return 'inline' (Week 14 plain site IDs) or 'coord_table' (*x suffix)."""
    if _INLINE_LAT.search(data) and data.find(b"\xff\xfe998x") < 0:
        pos = 0
        while True:
            pos = data.find(b"\xff\xfe", pos)
            if pos < 0:
                break
            j = pos + 2
            chars: list[str] = []
            while j < len(data) and 48 <= data[j] <= 57:
                chars.append(chr(data[j]))
                j += 1
            if _SITE_ID.match("".join(chars)):
                return "inline"
            pos += 2
    return "coord_table"


def _read_ascii_pushpin_name(data: bytes, start: int, suffix: str = "x") -> str:
    if data[start : start + 2] != b"\xff\xfe":
        return ""
    j = start + 2
    chars: list[str] = []
    while j < len(data) and (
        (48 <= data[j] <= 57) or (suffix and chars and data[j] == ord(suffix))
    ):
        chars.append(chr(data[j]))
        j += 1
    return "".join(chars)


def _extract_coord_table(ud: bytes, lo: int = 135000, hi: int = 150000) -> list[int]:
    offsets: list[int] = []
    last_off = -9999
    for i in range(lo, min(hi, len(ud) - 16)):
        lat, lon = struct.unpack_from("<dd", ud, i)
        if -125 < lon < -65 and 25 < lat < 50 and i - last_off > 80:
            offsets.append(i)
            last_off = i
    return offsets


def field_coords_from_stops(
    stops: list[dict],
    *,
    field_only: bool = False,
    installed_only: bool = False,
) -> dict[str, tuple[float, float]]:
    """Site id -> (lat, lon) for installed/skipped sites with field GPS."""
    out: dict[str, tuple[float, float]] = {}
    for s in stops:
        if installed_only and not s.get("installed"):
            continue
        if not installed_only and not (s.get("installed") or s.get("skipped")):
            continue
        lat = s.get("field_lat")
        lon = s.get("field_lon")
        if (lat is None or lon is None) and not field_only:
            lat = s.get("lat")
            lon = s.get("lon")
        if lat is None or lon is None:
            continue
        out[str(s.get("id", "")).strip()] = (float(lat), float(lon))
    return out


def field_coords_from_report(
    report_path: str,
    sheet: str,
    *,
    field_only: bool = False,
    installed_only: bool = False,
) -> dict[str, tuple[float, float]]:
    sheets = export.parse_report_workbook(report_path)
    stops = sheets.get(sheet, [])
    if not stops:
        raise ValueError(f"No sheet {sheet!r} in report {report_path}")
    return field_coords_from_stops(
        stops, field_only=field_only, installed_only=installed_only,
    )


def _patch_inline_site(data: bytearray, site_id: str, lat: float, lon: float) -> int:
    lat_s = _fmt_lat(lat)
    lon_s = _fmt_lon(lon)
    needle = b"\xff\xfe" + site_id.encode("ascii")
    pos = 0
    patched = 0
    while True:
        pos = data.find(needle, pos)
        if pos < 0:
            break
        after = pos + len(needle)
        if after < len(data) and 48 <= data[after] <= 57:
            pos += 2
            continue
        tail = data[pos : pos + 400]
        lat_m = _INLINE_LAT.search(tail)
        lon_m = _INLINE_LON.search(tail)
        if not lat_m or not lon_m:
            pos += 2
            continue
        la0 = pos + lat_m.start(1)
        lo0 = pos + lon_m.start(1)
        old_lat = data[la0 : la0 + lat_m.end(1) - lat_m.start(1)]
        old_lon = data[lo0 : lo0 + lon_m.end(1) - lon_m.start(1)]
        if len(lat_s) != len(old_lat) or len(lon_s) != len(old_lon):
            pos += 2
            continue
        data[la0 : la0 + len(lat_s)] = lat_s
        data[lo0 : lo0 + len(lon_s)] = lon_s
        patched += 1
        pos += 2
    return patched


def _patch_coord_table(
    data: bytearray,
    ud: bytearray,
    updates: dict[str, tuple[float, float]],
    suffix: str = "x",
) -> tuple[int, list[str]]:
    name_re = re.compile(rf"^\d+{re.escape(suffix)}$")
    offsets = _extract_coord_table(ud)
    if not offsets:
        return 0, ["No coordinate table found in UserData"]

    records: list[dict] = []
    pos = 0
    while True:
        pos = data.find(b"\xff\xfe", pos)
        if pos < 0:
            break
        name = _read_ascii_pushpin_name(data, pos, suffix)
        if not name_re.match(name):
            pos += 2
            continue
        tail = data[pos : pos + 80]
        marker = tail.find(b"\xef\x85\x03\x12")
        idx = struct.unpack_from("<H", tail, marker + 5)[0] if marker >= 0 else None
        records.append({"name": name, "site": name[: -len(suffix)], "idx": idx})
        pos += 2

    idx_vals = [r["idx"] for r in records if r["idx"] is not None]
    if not idx_vals:
        return 0, ["No pushpin index markers found"]
    origin = min(idx_vals)

    patched = 0
    warnings: list[str] = []
    for rec in records:
        site = rec["site"]
        if site not in updates or rec["idx"] is None:
            continue
        ci = rec["idx"] - origin
        if ci < 0 or ci >= len(offsets):
            warnings.append(f"Site {site}: coord index {ci} out of range")
            continue
        lat, lon = updates[site]
        struct.pack_into("<dd", ud, offsets[ci], lat, lon)
        patched += 1

    return patched, warnings


def apply_field_gps_to_est(
    est_path: str | Path,
    updates: dict[str, tuple[float, float]],
    out_path: str | Path | None = None,
) -> dict:
    """Patch .EST pushpins with field GPS. Returns summary dict."""
    src = Path(est_path)
    if not src.is_file():
        raise FileNotFoundError(est_path)
    dst = Path(out_path) if out_path else src.with_name(src.stem + "_FIELD.est")
    data = bytearray(src.read_bytes())
    fmt = detect_est_format(data)

    patched_sites: list[str] = []
    missing_in_est: list[str] = []
    no_gps: list[str] = []
    warnings: list[str] = []
    pin_count = 0

    if fmt == "inline":
        for site_id, (lat, lon) in sorted(
            updates.items(), key=lambda kv: len(kv[0]), reverse=True,
        ):
            n = _patch_inline_site(data, site_id, lat, lon)
            if n:
                patched_sites.append(site_id)
                pin_count += n
            else:
                missing_in_est.append(site_id)
        dst.write_bytes(data)
    else:
        import olefile

        ole = olefile.OleFileIO(str(src))
        ud = bytearray(ole.openstream("UserData").read())
        ole.close()
        pin_count, warnings = _patch_coord_table(data, ud, updates)
        patched_sites = []
        pos = 0
        raw_names: set[str] = set()
        while True:
            pos = data.find(b"\xff\xfe", pos)
            if pos < 0:
                break
            name = _read_ascii_pushpin_name(data, pos, "x")
            if name.endswith("x"):
                raw_names.add(name[:-1])
            pos += 2
        for site_id in updates:
            if site_id in raw_names:
                patched_sites.append(site_id)
            else:
                missing_in_est.append(site_id)
        ole = olefile.OleFileIO(str(src))
        ud_orig = ole.openstream("UserData").read()
        ole.close()
        if len(ud) != len(ud_orig):
            raise RuntimeError("UserData size changed — unsupported")
        raw = bytearray(src.read_bytes())
        idx = raw.find(ud_orig)
        if idx < 0:
            raise RuntimeError("Could not locate UserData stream in EST file")
        raw[idx : idx + len(ud)] = ud
        dst.write_bytes(raw)

    return {
        "source": str(src),
        "output": str(dst),
        "format": fmt,
        "sites_requested": len(updates),
        "sites_patched": len(patched_sites),
        "pins_patched": pin_count,
        "patched_sites": patched_sites,
        "missing_in_est": missing_in_est,
        "no_gps": no_gps,
        "warnings": warnings,
    }


def report_shared_coord_conflicts(
    est_path: str | Path,
    report_path: str,
    sheet: str,
) -> list[str]:
    """Sites that share EST coordinate slots but need different field GPS."""
    from collections import defaultdict

    src = Path(est_path)
    if not src.is_file():
        return []
    raw = src.read_bytes()
    coords = field_coords_from_report(
        report_path, sheet, field_only=True, installed_only=True,
    )
    lat_wants: dict[int, set[tuple[str, str]]] = defaultdict(set)
    lon_wants: dict[int, set[tuple[str, str]]] = defaultdict(set)
    for m in re.finditer(rb"\xff\xfe(\d{3,5})", raw):
        sid = m.group(1).decode()
        after = m.end()
        if after < len(raw) and 48 <= raw[after] <= 57:
            continue
        if sid not in coords:
            continue
        tail = raw[m.start() : m.start() + 400]
        lat_m = _INLINE_LAT.search(tail)
        lon_m = _INLINE_LON.search(tail)
        if not lat_m or not lon_m:
            continue
        flat, flon = coords[sid]
        lat_wants[m.start() + lat_m.start(1)].add((sid, _fmt_lat(flat).decode()))
        lon_wants[m.start() + lon_m.start(1)].add((sid, _fmt_lon(flon).decode()))

    lines: list[str] = []
    for label, wants in (("lat", lat_wants), ("lon", lon_wants)):
        for off, pairs in sorted(wants.items()):
            vals = {v for _, v in pairs}
            if len(vals) <= 1:
                continue
            sites = ", ".join(f"{s} ({v})" for s, v in sorted(pairs))
            lines.append(f"shared {label}: {sites}")
    return lines
