"""Week 17: one GPS CSV per site (street, begin, end, install).

Sources (disk-verified paths):
  - Week 17 Install Pins.html  (street + begin/end/install)
  - Week 17 IG TFC.xlsx        (cross-check install LAT/LON)
  - Week 17 Map 1.est          (optional: install pushpin presence)

Writes to:
  <work>/site_gps_csv/<site>_<street>.csv
  <work>/site_gps_csv/Week17_All_Sites_GPS.csv
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import openpyxl

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from core.est_viewer import pushpins_from_est  # noqa: E402

WORK = Path(r"C:\Users\isaac\Downloads\week 17 ig\week 17 ig")
HTML = WORK / "Week 17 Install Pins.html"
TFC = WORK / "Week 17 IG TFC.xlsx"
EST = WORK / "Week 17 Map 1.est"
OUT = WORK / "site_gps_csv"

ROWS_RE = re.compile(r"const rows = (\[.*?\]);", re.S)


def _site_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip()


def _safe_stem(street: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", (street or "UNKNOWN").strip(), flags=re.A)
    return re.sub(r"_+", "_", s).strip("_") or "UNKNOWN"


def load_html_rows(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = ROWS_RE.search(text)
    if not m:
        raise SystemExit(f"No const rows = [...] in {path}")
    rows = json.loads(m.group(1))
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"Empty rows list in {path}")
    return rows


def load_tfc_install(path: Path) -> dict[str, tuple[float, float]]:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    out: dict[str, tuple[float, float]] = {}
    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        if i == 1 or not row or row[1] is None:
            continue
        site = _site_str(row[1])
        lat, lon = row[9], row[10]
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            out[site] = (float(lat), float(lon))
    return out


def write_site_csv(path: Path, row: dict) -> None:
    site = _site_str(row.get("site"))
    street = str(row.get("street") or "").strip()
    points = [
        ("begin", row.get("begin_lat"), row.get("begin_lon")),
        ("end", row.get("end_lat"), row.get("end_lon")),
        ("install", row.get("install_lat"), row.get("install_lon")),
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["site", "street", "point", "lat", "lon"])
        for label, lat, lon in points:
            if lat is None or lon is None:
                continue
            w.writerow([site, street, label, f"{float(lat):.6f}", f"{float(lon):.6f}"])


def main() -> int:
    if not HTML.is_file():
        print(f"FAIL missing HTML: {HTML}")
        return 1
    if not TFC.is_file():
        print(f"FAIL missing TFC: {TFC}")
        return 1

    rows = load_html_rows(HTML)
    tfc = load_tfc_install(TFC)
    OUT.mkdir(parents=True, exist_ok=True)

    # Clear prior exports only inside site_gps_csv
    for old in OUT.glob("*.csv"):
        old.unlink()

    mismatches: list[str] = []
    written: list[Path] = []
    master_rows: list[list[str]] = []

    for row in sorted(rows, key=lambda r: (len(_site_str(r.get("site"))), _site_str(r.get("site")))):
        site = _site_str(row.get("site"))
        street = str(row.get("street") or "").strip()
        ilat = row.get("install_lat")
        ilon = row.get("install_lon")
        if site in tfc and ilat is not None and ilon is not None:
            tlat, tlon = tfc[site]
            if abs(tlat - float(ilat)) > 1e-6 or abs(tlon - float(ilon)) > 1e-6:
                mismatches.append(
                    f"{site}: HTML install ({ilat},{ilon}) != TFC ({tlat},{tlon})"
                )

        out_path = OUT / f"{site}_{_safe_stem(street)}.csv"
        write_site_csv(out_path, row)
        written.append(out_path)

        for label, lat_k, lon_k in (
            ("begin", "begin_lat", "begin_lon"),
            ("end", "end_lat", "end_lon"),
            ("install", "install_lat", "install_lon"),
        ):
            lat, lon = row.get(lat_k), row.get(lon_k)
            if lat is None or lon is None:
                continue
            master_rows.append(
                [site, street, label, f"{float(lat):.6f}", f"{float(lon):.6f}"]
            )

    master = OUT / "Week17_All_Sites_GPS.csv"
    with master.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["site", "street", "point", "lat", "lon"])
        w.writerows(master_rows)

    est_note = "EST not read"
    if EST.is_file():
        pins = pushpins_from_est(EST)
        est_note = f"EST pushpins={len(pins)} file={EST.name}"

    missing_seg = [
        _site_str(r.get("site"))
        for r in rows
        if r.get("begin_lat") is None or r.get("end_lat") is None
    ]

    print(f"OK sites={len(written)} out={OUT}")
    print(f"OK master={master.name} rows={len(master_rows)}")
    print(f"OK {est_note}")
    print(f"OK TFC install coords={len(tfc)}")
    if missing_seg:
        print(f"WARN missing begin/end: {', '.join(missing_seg)}")
    else:
        print("OK all sites have begin/end/install")
    if mismatches:
        print(f"WARN HTML vs TFC install mismatch ({len(mismatches)}):")
        for line in mismatches[:10]:
            print(" ", line)
        return 2
    print("OK HTML install matches TFC LAT/LON")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
