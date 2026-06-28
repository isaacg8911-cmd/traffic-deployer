"""Extract pushpin names and lat/lon from Microsoft Streets & Trips .est files."""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path


def read_ascii_pushpin_name(data: bytes, start: int) -> str:
    if data[start : start + 2] != b"\xff\xfe":
        return ""
    j = start + 2
    chars: list[str] = []
    while j < len(data) and ((48 <= data[j] <= 57) or (chars and data[j] == ord("x"))):
        chars.append(chr(data[j]))
        j += 1
    return "".join(chars)


def extract_coord_table(ud: bytes, lo: int = 135000, hi: int = 150000) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    last_off = -9999
    for i in range(lo, min(hi, len(ud) - 16)):
        lat, lon = struct.unpack_from("<dd", ud, i)
        if -125 < lon < -65 and 25 < lat < 50:
            if i - last_off > 80:
                coords.append((lat, lon))
                last_off = i
    return coords


def extract_pushpins(data: bytes, ud: bytes, suffix: str = "x") -> list[dict]:
    name_re = re.compile(rf"^\d+{re.escape(suffix)}$")
    coords = extract_coord_table(ud)
    records: list[dict] = []
    pos = 0
    while True:
        pos = data.find(b"\xff\xfe", pos)
        if pos < 0:
            break
        name = read_ascii_pushpin_name(data, pos)
        if not name_re.match(name):
            pos += 2
            continue
        tail = data[pos : pos + 80]
        marker = tail.find(b"\xef\x85\x03\x12")
        idx = struct.unpack_from("<H", tail, marker + 5)[0] if marker >= 0 else None
        records.append({"name": name, "idx": idx, "lat": None, "lon": None})
        pos += 2

    if not records or not coords:
        return records

    origin = min(r["idx"] for r in records if r["idx"] is not None)
    for r in records:
        if r["idx"] is None:
            continue
        ci = r["idx"] - origin
        if 0 <= ci < len(coords):
            r["lat"], r["lon"] = coords[ci]
    return records


def main() -> int:
    est_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"c:\Users\isaac\Downloads\Week 13 Day 1 Isaac (1).est"
    )
    suffix = sys.argv[2] if len(sys.argv) > 2 else "x"

    import olefile

    ole = olefile.OleFileIO(str(est_path))
    data = est_path.read_bytes()
    ud = ole.openstream("UserData").read()
    records = extract_pushpins(data, ud, suffix)
    matched = [r for r in records if r["lat"] is not None]

    print(f"File: {est_path.name}")
    print(f"Pushpins matching *{suffix}: {len(records)}")
    print(f"Coordinates resolved: {len(matched)}")
    print()
    print(f"{'Site':<8} {'Lat':>12} {'Lon':>12}  Google Maps")
    print("-" * 80)

    for r in sorted(records, key=lambda x: int(x["name"][:-1])):
        if r["lat"] is None:
            print(f"{r['name']:<8}  (coordinate not found)")
            continue
        maps = f"https://www.google.com/maps?q={r['lat']:.6f},{r['lon']:.6f}"
        print(f"{r['name']:<8} {r['lat']:12.6f} {r['lon']:12.6f}  {maps}")

    out_csv = est_path.with_name(est_path.stem + f"_sites_{suffix}.csv")
    lines = ["site,lat,lon,google_maps_url"]
    for r in sorted(records, key=lambda x: int(x["name"][:-1])):
        if r["lat"] is None:
            lines.append(f"{r['name']},,,")
        else:
            maps = f"https://www.google.com/maps?q={r['lat']:.6f},{r['lon']:.6f}"
            lines.append(f"{r['name']},{r['lat']:.6f},{r['lon']:.6f},{maps}")
    out_csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {out_csv}")
    return 0 if len(matched) == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
