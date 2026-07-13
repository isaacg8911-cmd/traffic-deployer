"""Week 17: EST with drop/install pins + HTML labeled by site number.

Writes into the week 17 work folder:
  - Week 17 Map 1_DROP_PINS.est  (pushpins moved to TFC LAT/LON)
  - Week 17 Install Pins.html    (Leaflet map, site number on each pin)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from core.est_field_gps import apply_field_gps_to_est  # noqa: E402
from core.est_viewer import pushpins_from_est  # noqa: E402

WORK = Path(r"C:\Users\isaac\Downloads\week 17 ig\week 17 ig")
TFC = WORK / "Week 17 IG TFC.xlsx"
EST = WORK / "Week 17 Map 1.est"
EST_OUT = WORK / "Week 17 Map 1_DROP_PINS.est"
HTML_OUT = WORK / "Week 17 Install Pins.html"
REPORT = WORK / "week17_install_pins_report.txt"


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


def load_install_rows(path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(path, data_only=True)
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
            # still allow GPS rows for map; prefer install/skip markings
            if not _mark(row[6]):
                continue
        status = "skipped" if _mark(row[7]) else "installed"
        dirs = str(row[3] or "").strip()
        rows.append({
            "site": site,
            "street": dirs or f"Site {site}",
            "install_lat": float(lat),
            "install_lon": float(lon),
            "status": status,
            "serial": _site_str(row[2]) if row[2] is not None else "",
            "notes": str(row[5] or "").strip(),
        })
    rows.sort(key=lambda r: (len(r["site"]), r["site"]))
    return rows


def write_clickable_html(path: Path, rows: list[dict]) -> None:
    data = json.dumps(rows)
    avg_lat = sum(r["install_lat"] for r in rows) / len(rows)
    avg_lon = sum(r["install_lon"] for r in rows) / len(rows)
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
      background: #fff; padding: 10px 12px; border-radius: 10px;
      box-shadow: 0 2px 12px #0003; font: 14px system-ui, sans-serif; max-width: 280px;
    }}
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="panel">
    <b>Week 17 Install Pins</b><br>
    {len(rows)} pins with site numbers.<br>
    Green = installed · Gray = skipped.<br>
    Click a pin for GPS + directions.
  </div>
  <script>
    const rows = {data};
    const map = L.map('map').setView([{avg_lat:.6f}, {avg_lon:.6f}], 12);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap'
    }}).addTo(map);
    const bounds = [];
    for (const r of rows) {{
      const ll = [r.install_lat, r.install_lon];
      bounds.push(ll);
      const color = r.status === 'skipped' ? '#78909c' : '#2e7d32';
      L.circleMarker(ll, {{
        radius: 8, color: '#fff', weight: 2, fillColor: color, fillOpacity: 0.95
      }})
        .bindPopup(
          '<b>Site ' + r.site + '</b><br>' +
          (r.street || '') + '<br>' +
          'Install GPS: ' + Number(r.install_lat).toFixed(6) + ', ' +
          Number(r.install_lon).toFixed(6) +
          (r.serial ? '<br>Serial: ' + r.serial : '') +
          (r.notes ? '<br>Notes: ' + r.notes : '') +
          '<br><a target="_blank" rel="noopener" href="https://www.google.com/maps?q=' +
          r.install_lat + ',' + r.install_lon + '">Google Maps</a>'
        )
        .addTo(map);
      L.marker(ll, {{
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


def main() -> int:
    lines: list[str] = ["=== Week 17 install / drop pin exports ==="]

    if not TFC.is_file():
        print(f"Missing TFC: {TFC}", file=sys.stderr)
        return 2
    if not EST.is_file():
        print(f"Missing EST: {EST}", file=sys.stderr)
        return 2

    rows = load_install_rows(TFC)
    if not rows:
        print("No install rows with LAT/LON in TFC", file=sys.stderr)
        return 3

    updates = {r["site"]: (r["install_lat"], r["install_lon"]) for r in rows}
    patch = apply_field_gps_to_est(EST, updates, EST_OUT)
    write_clickable_html(HTML_OUT, rows)

    # verify patched EST reads back near TFC coords
    verify_ok = 0
    verify_miss: list[str] = []
    if EST_OUT.is_file():
        pinned = {p["site"]: p for p in pushpins_from_est(EST_OUT)}
        for site, (lat, lon) in updates.items():
            p = pinned.get(site)
            if not p:
                verify_miss.append(site)
                continue
            if abs(p["lat"] - lat) < 0.001 and abs(p["lon"] - lon) < 0.001:
                verify_ok += 1
            else:
                verify_miss.append(
                    f"{site}(est={p['lat']:.5f},{p['lon']:.5f} tfc={lat:.5f},{lon:.5f})"
                )

    lines.append(f"Install/skip pins from TFC: {len(rows)}")
    lines.append(
        f"EST patch: {patch['sites_patched']}/{patch['sites_requested']} "
        f"format={patch['format']} pins_touched={patch['pins_patched']}"
    )
    if patch["missing_in_est"]:
        lines.append("Missing in EST: " + ", ".join(patch["missing_in_est"]))
    lines.append(f"Verify EST~TFC: {verify_ok}/{len(updates)}")
    if verify_miss:
        lines.append("Verify misses: " + ", ".join(verify_miss[:15]))
    lines.append(f"Wrote: {EST_OUT}")
    lines.append(f"Wrote: {HTML_OUT}")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        print(line.encode("ascii", "replace").decode("ascii"))
    return 0 if patch["sites_patched"] and verify_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
