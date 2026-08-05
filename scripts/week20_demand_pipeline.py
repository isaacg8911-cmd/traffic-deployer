"""Week 20 DEMAND: Apple install pins + downloaded .tvp sites -> handoff trio.

Inputs:
  Downloads/Week 20 - Apple Maps.mht
  Downloads/Week 20 Day 1 Isaac.est
  Downloads/Week 20 Isaacx.xls
  Desktop/week 20 ig/*.tvp  (or Downloads/week 20 ig/*.tvp)

Outputs (Desktop/week 20 ig/ and Downloads/week 20 ig/):
  Week 20 IG TFC.xlsx
  Week 20 Install Pins.html
  Week 20 Map 1.est
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.styles import Font

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from core.direction import infer_from_segment  # noqa: E402
from core.est_field_gps import apply_field_gps_to_est  # noqa: E402
from core.est_viewer import (  # noqa: E402
    COLOR_BEGIN,
    COLOR_END,
    COLOR_FIELD,
    pushpins_from_est,
)
from scripts.week17_segment_match import (  # noqa: E402
    extract_apple_places,
    match_apple_to_segments,
)

MHT = Path(r"c:\Users\isaac\Downloads\Week 20 - Apple Maps.mht")
EST_SRC = Path(r"c:\Users\isaac\Downloads\Week 20 Day 1 Isaac.est")
XLS = Path(r"c:\Users\isaac\Downloads\Week 20 Isaacx.xls")
WORK_DL = Path(r"c:\Users\isaac\Downloads\week 20 ig")
WORK_DESK = Path(r"c:\Users\isaac\OneDrive\Desktop\week 20 ig")

# From Director screenshot (Desktop/week 20 ig) when .tvp not yet on this machine.
TVP_FALLBACK = [
    ("18371", "e", date(2026, 7, 31)),
    ("18380", "e", date(2026, 7, 31)),
    ("18384", "n", date(2026, 7, 31)),
    ("18387", "e", date(2026, 7, 31)),
    ("18388", "e", date(2026, 7, 31)),
    ("18389", "n", date(2026, 7, 31)),
    ("18393", "e", date(2026, 7, 31)),
    ("18397", "n", date(2026, 7, 31)),
    ("18399", "n", date(2026, 7, 31)),
    ("18402", "n", date(2026, 7, 31)),
    ("18406", "n", date(2026, 7, 31)),
    ("18412", "n", date(2026, 7, 31)),
    ("18415", "n", date(2026, 7, 31)),
    ("18421", "n", date(2026, 7, 31)),
    ("18423", "n", date(2026, 7, 31)),
    ("18425", "e", date(2026, 7, 31)),
    ("18432", "e", date(2026, 7, 31)),
]

TVP_RE = re.compile(r"^(\d{4,5})([en])c", re.I)

HEADERS = [
    "Date", "Site", "Serial", "Directions", "Lanes", "Notes",
    "Installed", "Skipped", "Picked up", "LAT", "LON",
]
SHEET = "Week 20 Day 1 Isaac"


def _site_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip()


def discover_tvp_dirs() -> list[Path]:
    dirs = []
    for p in (WORK_DESK, WORK_DL):
        if p.is_dir():
            dirs.append(p)
    return dirs


def load_tvp_installs() -> tuple[dict[str, dict], str]:
    """Return {site: {direction, date, file}} and source label."""
    found: dict[str, dict] = {}
    for folder in discover_tvp_dirs():
        for p in folder.glob("*.tvp"):
            m = TVP_RE.match(p.name)
            if not m:
                continue
            sid = m.group(1)
            direction = m.group(2).lower()
            ts = datetime.fromtimestamp(p.stat().st_mtime).date()
            found[sid] = {"direction": direction, "date": ts, "file": p.name}
        if found:
            return found, f"disk:{folder}"

    # Screenshot inventory (field laptop / not synced yet)
    out = {
        sid: {"direction": d, "date": dt, "file": f"{sid}{d}c1b.tvp"}
        for sid, d, dt in TVP_FALLBACK
    }
    return out, "screenshot-fallback"


def load_day1_sites(xls_path: Path) -> dict[str, dict]:
    df = pd.read_excel(xls_path, sheet_name="Day 1")
    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        sid = _site_str(row.get("tds"))
        if not sid:
            continue
        try:
            blat = float(row["Begin_Lat"])
            blon = float(row["Begin_Lon"])
            elat = float(row["End_Lat"])
            elon = float(row["End_Lon"])
        except (TypeError, ValueError, KeyError):
            continue
        lanes = row.get("Through_Lanes")
        try:
            lanes_n = int(lanes) if pd.notna(lanes) else 2
        except (TypeError, ValueError):
            lanes_n = 2
        hint = infer_from_segment(blat, blon, elat, elon)
        out[sid] = {
            "site": sid,
            "street": str(row.get("Street") or "").strip(),
            "begin_lat": blat,
            "begin_lon": blon,
            "end_lat": elat,
            "end_lon": elon,
            "lat": (blat + elat) / 2,
            "lon": (blon + elon) / 2,
            "lanes": lanes_n,
            "seg_direction": hint.get("direction") or "",
        }
    return out


def write_tfc(path: Path, rows: list[dict], sheet_name: str) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = (sheet_name or "Week 20")[:31]
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        site = int(r["site"]) if str(r["site"]).isdigit() else r["site"]
        serial = r.get("serial")
        if serial and str(serial).isdigit():
            serial = int(serial)
        ws.append([
            r.get("date"),
            site,
            serial,
            r.get("directions") or None,
            r.get("lanes"),
            r.get("notes") or None,
            "x" if r.get("installed") else None,
            "x" if r.get("skipped") else None,
            "x" if r.get("picked_up") else None,
            r.get("lat"),
            r.get("lon"),
        ])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def write_clickable_html(path: Path, rows: list[dict]) -> None:
    data = json.dumps(rows)
    avg_lat = sum(r["install_lat"] for r in rows) / len(rows)
    avg_lon = sum(r["install_lon"] for r in rows) / len(rows)
    with_seg = sum(1 for r in rows if "begin_lat" in r and "end_lat" in r)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Week 20 Install Pins</title>
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
      box-shadow: 0 2px 12px #0003; font: 13px/1.45 system-ui, sans-serif; max-width: 320px;
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
    <b>Week 20 Install Pins</b><br>
    {len(rows)} downloaded sites · {with_seg} with begin/end.<br>
    <span class="legend">
      <span style="background:{COLOR_BEGIN}"></span>Begin
      <span style="background:{COLOR_END}; margin-left:8px"></span>End
      <span style="background:{COLOR_FIELD}; margin-left:8px"></span>Install
    </span><br>
    Site number on install pin. Click for GPS / Google Maps.
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
        (r.direction ? '<br>Direction: ' + r.direction : '') +
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
      if (r.begin_lat != null && r.end_lat != null) {{
        L.polyline(
          [[r.begin_lat, r.begin_lon], [r.end_lat, r.end_lon]],
          {{ color: '#90a4ae', weight: 2, opacity: 0.7, dashArray: '4 5' }}
        ).addTo(map);
        addDot(r.begin_lat, r.begin_lon, '{COLOR_BEGIN}', r, 'Begin', 6);
        addDot(r.end_lat, r.end_lon, '{COLOR_END}', r, 'End', 6);
      }}
      addDot(r.install_lat, r.install_lon, '{COLOR_FIELD}', r, 'Install', 8);
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


def _write_pair(path: Path, rows_tfc, html_rows, est_src, updates, lines) -> dict:
    """Write TFC + HTML + EST into one folder."""
    tfc = path / "Week 20 IG TFC.xlsx"
    html = path / "Week 20 Install Pins.html"
    est = path / "Week 20 Map 1.est"
    write_tfc(tfc, rows_tfc, SHEET)
    write_clickable_html(html, html_rows)
    shutil.copy2(est_src, est)
    patch = apply_field_gps_to_est(est, updates, est)
    pinned = {p["site"]: p for p in pushpins_from_est(str(est))}
    verify_ok = 0
    for sid, (lat, lon) in updates.items():
        p = pinned.get(sid)
        if p and abs(p["lat"] - lat) < 0.001 and abs(p["lon"] - lon) < 0.001:
            verify_ok += 1
    lines.append(f"Wrote into {path}:")
    lines.append(f"  {tfc.name}")
    lines.append(f"  {html.name}")
    lines.append(
        f"  {est.name}  patch {patch['sites_patched']}/{patch['sites_requested']} "
        f"verify {verify_ok}/{len(updates)}"
    )
    return {
        "patch": patch,
        "verify_ok": verify_ok,
        "updates_n": len(updates),
    }


def main() -> int:
    lines: list[str] = ["=== Week 20 DEMAND pipeline (TVP install truth) ==="]
    for p in (MHT, EST_SRC, XLS):
        if not p.is_file():
            print(f"Missing input: {p}", file=sys.stderr)
            return 2

    WORK_DL.mkdir(parents=True, exist_ok=True)
    WORK_DESK.mkdir(parents=True, exist_ok=True)

    tvps, tvp_src = load_tvp_installs()
    lines.append(f"TVP installs: {len(tvps)} from {tvp_src}")
    for sid in sorted(tvps, key=lambda x: (len(x), x)):
        t = tvps[sid]
        lines.append(f"  {sid} dir={t['direction']} date={t['date']} file={t['file']}")

    day1 = load_day1_sites(XLS)
    pins = {p["site"]: p for p in pushpins_from_est(str(EST_SRC))}
    lines.append(f"XLS Day1={len(day1)} EST pins={len(pins)}")

    missing_day1 = sorted(set(tvps) - set(day1))
    if missing_day1:
        lines.append(f"ERROR TVP not on Day1 XLS: {missing_day1}")
        return 3

    apple = extract_apple_places(MHT)
    (WORK_DL / "_apple_places.json").write_text(json.dumps(apple, indent=2), encoding="utf-8")
    sites = {sid: day1[sid] for sid in pins if sid in day1}
    matches = match_apple_to_segments(apple, sites, prefer_ids=set(tvps) & set(sites))
    (WORK_DL / "_apple_segment_matches.json").write_text(
        json.dumps(matches, indent=2), encoding="utf-8"
    )
    apple_coords = {
        m["site"]: (m["lat"], m["lon"])
        for m in matches
        if m.get("accepted") and m.get("site")
    }
    apple_names = {
        m["site"]: m.get("name") or ""
        for m in matches
        if m.get("accepted") and m.get("site")
    }
    lines.append(f"Apple places={len(apple)} matched to segments={len(apple_coords)}")
    lines.append(
        f"TVP with Apple pin: {sorted(set(tvps) & set(apple_coords))} "
        f"({len(set(tvps) & set(apple_coords))})"
    )
    no_apple = sorted(set(tvps) - set(apple_coords))
    lines.append(f"TVP without Apple pin (EST fallback): {no_apple}")

    # Install order: Apple guide order for TVP sites, then remaining TVP, then unmarked Day1
    apple_order = [m["site"] for m in matches if m.get("site") in tvps and m.get("accepted")]
    rest_tvp = sorted(set(tvps) - set(apple_order), key=lambda x: (len(x), x))
    install_order = apple_order + rest_tvp

    coords: dict[str, tuple[float, float]] = {}
    coord_src: dict[str, str] = {}
    for sid in install_order:
        if sid in apple_coords:
            coords[sid] = apple_coords[sid]
            coord_src[sid] = "apple"
        elif sid in pins:
            coords[sid] = (pins[sid]["lat"], pins[sid]["lon"])
            coord_src[sid] = "est"
        else:
            s = day1[sid]
            coords[sid] = (s["lat"], s["lon"])
            coord_src[sid] = "xls-mid"
        lines.append(
            f"  GPS {sid}: {coords[sid][0]:.6f},{coords[sid][1]:.6f} src={coord_src[sid]}"
        )

    rows: list[dict] = []
    html_rows: list[dict] = []
    for sid in install_order:
        s = day1[sid]
        t = tvps[sid]
        lat, lon = coords[sid]
        note = apple_names.get(sid) or None
        if coord_src[sid] != "apple":
            note = (note + " · " if note else "") + f"GPS from {coord_src[sid]} (no Apple pin)"
        rows.append({
            "date": t["date"],
            "site": sid,
            "serial": None,
            "directions": t["direction"],
            "lanes": s["lanes"],
            "notes": note,
            "installed": True,
            "skipped": False,
            "picked_up": True,
            "lat": lat,
            "lon": lon,
        })
        html_rows.append({
            "site": sid,
            "street": s["street"],
            "install_lat": lat,
            "install_lon": lon,
            "status": "installed",
            "direction": t["direction"],
            "notes": note or "",
            "begin_lat": round(s["begin_lat"], 6),
            "begin_lon": round(s["begin_lon"], 6),
            "end_lat": round(s["end_lat"], 6),
            "end_lon": round(s["end_lon"], 6),
        })

    remaining = sorted(set(day1) - set(tvps), key=lambda x: (len(x), x))
    for sid in remaining:
        s = day1[sid]
        rows.append({
            "date": None,
            "site": sid,
            "serial": None,
            "directions": s["seg_direction"],
            "lanes": s["lanes"],
            "notes": None,
            "installed": False,
            "skipped": False,
            "picked_up": False,
            "lat": None,
            "lon": None,
        })

    lines.append(
        f"TFC rows: {len(install_order)} installed+picked_up, {len(remaining)} unmarked"
    )

    r1 = _write_pair(WORK_DL, rows, html_rows, EST_SRC, coords, lines)
    r2 = _write_pair(WORK_DESK, rows, html_rows, EST_SRC, coords, lines)

    report = "\n".join(lines) + "\n"
    (WORK_DL / "week20_demand_report.txt").write_text(report, encoding="utf-8")
    (WORK_DESK / "week20_demand_report.txt").write_text(report, encoding="utf-8")
    sys.stdout.buffer.write(report.encode("utf-8", errors="replace"))

    ok = (
        len(install_order) == len(tvps)
        and r1["verify_ok"] == r1["updates_n"]
        and r2["verify_ok"] == r2["updates_n"]
        and r1["patch"]["sites_patched"] == r1["updates_n"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
