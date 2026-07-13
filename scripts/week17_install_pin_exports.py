"""Week 17: EST drop/install pins + HTML with begin / end / install pins.

Writes into the week 17 work folder (no backups / report junk):
  - Week 17 Map 1.est           (pushpins at TFC LAT/LON; optional re-patch)
  - Week 17 Install Pins.html   (begin + end + install, site numbers)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from core import ingest  # noqa: E402
from core.est_field_gps import apply_field_gps_to_est  # noqa: E402
from core.est_viewer import pushpins_from_est  # noqa: E402
from core.est_viewer import COLOR_BEGIN, COLOR_END, COLOR_FIELD  # noqa: E402

WORK = Path(r"C:\Users\isaac\Downloads\week 17 ig\week 17 ig")
TFC = WORK / "Week 17 IG TFC.xlsx"
XLS = Path(r"C:\Users\isaac\Downloads\Week 17 Isaacx.xls")
EST = WORK / "Week 17 Map 1.est"
HTML_OUT = WORK / "Week 17 Install Pins.html"


def _mark(v) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in {"x", "1", "true", "yes", "y"}


def _site_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip()


def load_install_rows(tfc_path: Path, xls_path: Path) -> list[dict]:
    excel = ingest.parse_excel_sites([str(xls_path)]) if xls_path.is_file() else {}
    wb = openpyxl.load_workbook(tfc_path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows: list[dict] = []
    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        if i == 1 or not row or row[1] is None:
            continue
        site = _site_str(row[1])
        lat, lon = row[9], row[10]
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        if not (_mark(row[6]) or _mark(row[7])):
            if not _mark(row[6]):
                continue
        status = "skipped" if _mark(row[7]) else "installed"
        dirs = str(row[3] or "").strip()
        ex = excel.get(site) or {}
        begin_lat = ex.get("begin_lat")
        begin_lon = ex.get("begin_lon")
        end_lat = ex.get("end_lat")
        end_lon = ex.get("end_lon")
        street = str(ex.get("street") or dirs or f"Site {site}").strip()
        rec = {
            "site": site,
            "street": street,
            "install_lat": float(lat),
            "install_lon": float(lon),
            "status": status,
            "serial": _site_str(row[2]) if row[2] is not None else "",
            "notes": str(row[5] or "").strip(),
        }
        if begin_lat is not None and begin_lon is not None:
            rec["begin_lat"] = round(float(begin_lat), 6)
            rec["begin_lon"] = round(float(begin_lon), 6)
        if end_lat is not None and end_lon is not None:
            rec["end_lat"] = round(float(end_lat), 6)
            rec["end_lon"] = round(float(end_lon), 6)
        rows.append(rec)
    rows.sort(key=lambda r: (len(r["site"]), r["site"]))
    return rows


def write_clickable_html(path: Path, rows: list[dict]) -> None:
    data = json.dumps(rows)
    avg_lat = sum(r["install_lat"] for r in rows) / len(rows)
    avg_lon = sum(r["install_lon"] for r in rows) / len(rows)
    with_seg = sum(1 for r in rows if "begin_lat" in r and "end_lat" in r)
    path.write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Week 17 Install Pins</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    html, body, #map {{ height: 100%; margin: 0; }}
    .site-label {{
      font: 700 12px system-ui, sans-serif;
      color: #102a43;
      text-shadow: 0 0 3px #fff, 0 1px 2px #fff, 1px 0 2px #fff;
      white-space: nowrap;
    }}
    .panel {{
      position: absolute; left: 12px; top: 12px; z-index: 500;
      background: rgba(255,255,255,0.96); padding: 10px 12px; border-radius: 10px;
      box-shadow: 0 2px 12px #0003; font: 13px/1.45 system-ui, sans-serif; max-width: 300px;
    }}
    .legend span {{
      display: inline-block; width: 10px; height: 10px; border-radius: 50%;
      margin-right: 4px; vertical-align: middle; border: 1px solid rgba(0,0,0,0.15);
    }}
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="panel">
    <b>Week 17 Install Pins</b><br>
    {len(rows)} sites · {with_seg} with begin/end.<br>
    <span class="legend">
      <span style="background:{COLOR_BEGIN}"></span>Begin
      <span style="background:{COLOR_END}; margin-left:8px"></span>End
      <span style="background:{COLOR_FIELD}; margin-left:8px"></span>Install
    </span><br>
    Site number sits on the install pin. Click any point for details.
  </div>
  <script>
    const rows = {data};
    const map = L.map('map').setView([{avg_lat:.6f}, {avg_lon:.6f}], 12);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap'
    }}).addTo(map);
    const bounds = [];
    function popup(r, label, lat, lon) {{
      return '<b>Site ' + r.site + '</b> — ' + (r.street || '') +
        '<br><b>' + label + ':</b> ' + Number(lat).toFixed(6) + ', ' + Number(lon).toFixed(6) +
        (r.serial ? '<br>Serial: ' + r.serial : '') +
        (r.notes ? '<br>Notes: ' + r.notes : '') +
        '<br><a target="_blank" rel="noopener" href="https://www.google.com/maps?q=' +
        lat + ',' + lon + '">Google Maps</a>';
    }}
    function addDot(lat, lon, color, r, label, radius) {{
      const m = L.circleMarker([lat, lon], {{
        radius: radius, color: '#fff', weight: 2, fillColor: color, fillOpacity: 0.95
      }}).addTo(map);
      m.bindPopup(popup(r, label, lat, lon));
      bounds.push([lat, lon]);
    }}
    for (const r of rows) {{
      const hasSeg = r.begin_lat != null && r.end_lat != null;
      if (hasSeg) {{
        L.polyline(
          [[r.begin_lat, r.begin_lon], [r.end_lat, r.end_lon]],
          {{ color: '#90a4ae', weight: 2, opacity: 0.7, dashArray: '4 5' }}
        ).addTo(map);
        addDot(r.begin_lat, r.begin_lon, '{COLOR_BEGIN}', r, 'Begin', 6);
        addDot(r.end_lat, r.end_lon, '{COLOR_END}', r, 'End', 6);
      }}
      const installColor = r.status === 'skipped' ? '#78909c' : '{COLOR_FIELD}';
      addDot(r.install_lat, r.install_lon, installColor, r, 'Install', 8);
      L.marker([r.install_lat, r.install_lon], {{
        icon: L.divIcon({{
          className: 'site-label',
          html: r.site,
          iconSize: [52, 16],
          iconAnchor: [-10, 8]
        }})
      }}).addTo(map);
    }}
    if (bounds.length) map.fitBounds(bounds, {{ padding: [36, 36] }});
  </script>
</body>
</html>
""",
        encoding="utf-8",
    )


def main(argv: list[str]) -> int:
    html_only = "--html-only" in argv

    if not TFC.is_file():
        print(f"Missing TFC: {TFC}", file=sys.stderr)
        return 2
    if not html_only and not EST.is_file():
        print(f"Missing EST: {EST}", file=sys.stderr)
        return 2
    if not XLS.is_file():
        print(f"Missing Excel: {XLS}", file=sys.stderr)
        return 2

    rows = load_install_rows(TFC, XLS)
    if not rows:
        print("No install rows with LAT/LON in TFC", file=sys.stderr)
        return 3

    with_seg = sum(1 for r in rows if "begin_lat" in r and "end_lat" in r)
    write_clickable_html(HTML_OUT, rows)
    print(f"Install pins: {len(rows)}  begin/end: {with_seg}")
    print(f"Wrote: {HTML_OUT}")

    if html_only:
        return 0

    updates = {r["site"]: (r["install_lat"], r["install_lon"]) for r in rows}
    # Patch in place — no backup / DROP_PINS copy
    patch = apply_field_gps_to_est(EST, updates, EST)
    verify_ok = 0
    pinned = {p["site"]: p for p in pushpins_from_est(EST)}
    for site, (lat, lon) in updates.items():
        p = pinned.get(site)
        if p and abs(p["lat"] - lat) < 0.001 and abs(p["lon"] - lon) < 0.001:
            verify_ok += 1
    print(
        f"EST patch: {patch['sites_patched']}/{patch['sites_requested']} "
        f"verify {verify_ok}/{len(updates)}"
    )
    print(f"Wrote: {EST}")
    return 0 if patch["sites_patched"] and verify_ok == len(updates) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
