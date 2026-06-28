"""Read pushpin coordinates from Streets & Trips .est files → HTML / KML viewers."""
from __future__ import annotations

import html as html_lib
import json
import re
import struct
from pathlib import Path

from core.est_field_gps import _INLINE_LAT, _INLINE_LON, detect_est_format

_SITE_ID = re.compile(r"^\d{3,5}$")

# Match in-app map colors (web/app.js).
COLOR_BEGIN = "#1565c0"
COLOR_END = "#c62828"
COLOR_FIELD = "#43a047"


def pushpins_from_est(est_path: str | Path) -> list[dict]:
    """Return [{site, lat, lon}, ...] sorted by site id."""
    path = Path(est_path)
    if not path.is_file():
        raise FileNotFoundError(est_path)
    data = path.read_bytes()
    fmt = detect_est_format(data)
    if fmt == "inline":
        pins = _pushpins_inline(data)
    else:
        pins = _pushpins_coord_table(path, data)
    pins.sort(key=lambda p: (len(str(p["site"])), str(p["site"])))
    return pins


def sites_from_stops(stops: list[dict]) -> list[dict]:
    """Build handoff map records: begin/end + optional field GPS + status."""
    out: list[dict] = []
    for s in stops:
        sid = str(s.get("id", "")).strip()
        if not sid:
            continue
        if s.get("installed"):
            status = "installed"
        elif s.get("skipped"):
            status = "skipped"
        else:
            status = "pending"

        begin_lat = s.get("begin_lat")
        begin_lon = s.get("begin_lon")
        end_lat = s.get("end_lat")
        end_lon = s.get("end_lon")
        if begin_lat is None or begin_lon is None:
            begin_lat = s.get("lat")
            begin_lon = s.get("lon")
        if end_lat is None or end_lon is None:
            end_lat = begin_lat
            end_lon = begin_lon
        if begin_lat is None or begin_lon is None:
            continue

        rec: dict = {
            "site": sid,
            "street": str(s.get("street", "") or f"Site {sid}").strip(),
            "status": status,
            "begin_lat": round(float(begin_lat), 6),
            "begin_lon": round(float(begin_lon), 6),
            "end_lat": round(float(end_lat), 6),
            "end_lon": round(float(end_lon), 6),
        }
        if status == "installed":
            flat, flon = s.get("field_lat"), s.get("field_lon")
            if flat is not None and flon is not None:
                rec["field_lat"] = round(float(flat), 6)
                rec["field_lon"] = round(float(flon), 6)
        out.append(rec)
    out.sort(key=lambda r: (len(str(r["site"])), str(r["site"])))
    return out


def _pushpins_inline(data: bytes) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    pos = 0
    while True:
        pos = data.find(b"\xff\xfe", pos)
        if pos < 0:
            break
        j = pos + 2
        digits: list[str] = []
        while j < len(data) and 48 <= data[j] <= 57:
            digits.append(chr(data[j]))
            j += 1
        site = "".join(digits)
        if not _SITE_ID.match(site) or site in seen:
            pos += 2
            continue
        tail = data[pos : pos + 400]
        lat_m = _INLINE_LAT.search(tail)
        lon_m = _INLINE_LON.search(tail)
        if not lat_m or not lon_m:
            pos += 2
            continue
        seen.add(site)
        out.append({
            "site": site,
            "lat": float(lat_m.group(1)),
            "lon": float(lon_m.group(1)),
        })
        pos += 2
    return out


def _pushpins_coord_table(path: Path, data: bytes) -> list[dict]:
    try:
        import olefile
    except ImportError as exc:
        raise RuntimeError("coord_table .est requires olefile") from exc

    ole = olefile.OleFileIO(str(path))
    ud = ole.openstream("UserData").read()
    ole.close()

    offsets: list[int] = []
    last_off = -9999
    for i in range(135000, min(150000, len(ud) - 16)):
        lat, lon = struct.unpack_from("<dd", ud, i)
        if -125 < lon < -65 and 25 < lat < 50 and i - last_off > 80:
            offsets.append(i)
            last_off = i

    name_re = re.compile(r"^\d+x$")
    records: list[dict] = []
    pos = 0
    while True:
        pos = data.find(b"\xff\xfe", pos)
        if pos < 0:
            break
        j = pos + 2
        chars: list[str] = []
        while j < len(data) and ((48 <= data[j] <= 57) or (chars and data[j] == ord("x"))):
            chars.append(chr(data[j]))
            j += 1
        name = "".join(chars)
        if not name_re.match(name):
            pos += 2
            continue
        tail = data[pos : pos + 80]
        marker = tail.find(b"\xef\x85\x03\x12")
        idx = struct.unpack_from("<H", tail, marker + 5)[0] if marker >= 0 else None
        records.append({"site": name[:-1], "idx": idx})
        pos += 2

    idx_vals = [r["idx"] for r in records if r["idx"] is not None]
    if not idx_vals or not offsets:
        return []
    origin = min(idx_vals)
    out: list[dict] = []
    for rec in records:
        if rec["idx"] is None:
            continue
        ci = rec["idx"] - origin
        if 0 <= ci < len(offsets):
            lat, lon = struct.unpack_from("<dd", ud, offsets[ci])
            out.append({"site": rec["site"], "lat": lat, "lon": lon})
    return out


def _status_label(status: str) -> str:
    return {
        "installed": "Installed",
        "skipped": "Skipped",
        "pending": "Not completed",
    }.get(status, status.title())


def to_kml(sites: list[dict], *, title: str = "EST map") -> str:
    """KML 2.2 with begin/end/field styles."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        "<Document>",
        f"<name>{html_lib.escape(title)}</name>",
        "<Style id=\"begin\"><IconStyle><color>ffff0000</color><scale>0.8</scale></IconStyle></Style>",
        "<Style id=\"end\"><IconStyle><color>ff0000ff</color><scale>0.8</scale></IconStyle></Style>",
        "<Style id=\"field\"><IconStyle><color>ff00aa43</color><scale>0.9</scale></IconStyle></Style>",
    ]
    for site in sites:
        sid = html_lib.escape(str(site["site"]))
        folder = f"Site {sid}"
        lines.append(f"<Folder><name>{folder}</name>")
        blat, blon = site["begin_lat"], site["begin_lon"]
        elat, elon = site["end_lat"], site["end_lon"]
        status = _status_label(str(site.get("status", "")))
        street = html_lib.escape(str(site.get("street", "")))
        desc = f"{status} — {street}"
        lines.extend([
            "<Placemark><name>Begin</name><description>"
            f"{desc}</description><styleUrl>#begin</styleUrl><Point><coordinates>"
            f"{blon:.6f},{blat:.6f},0</coordinates></Point></Placemark>",
            "<Placemark><name>End</name><description>"
            f"{desc}</description><styleUrl>#end</styleUrl><Point><coordinates>"
            f"{elon:.6f},{elat:.6f},0</coordinates></Point></Placemark>",
        ])
        if site.get("field_lat") is not None:
            flat, flon = site["field_lat"], site["field_lon"]
            lines.append(
                "<Placemark><name>Installed GPS</name><description>"
                f"{desc}</description><styleUrl>#field</styleUrl><Point><coordinates>"
                f"{flon:.6f},{flat:.6f},0</coordinates></Point></Placemark>",
            )
        lines.append("</Folder>")
    lines.extend(["</Document>", "</kml>"])
    return "\n".join(lines) + "\n"


def to_html_map(sites: list[dict], *, title: str = "EST map") -> str:
    """Interactive HTML — blue begin, red end, green installed GPS."""
    if not sites:
        return _empty_html(title)
    safe_title = html_lib.escape(title)
    lats: list[float] = []
    lons: list[float] = []
    for s in sites:
        lats.extend([s["begin_lat"], s["end_lat"]])
        lons.extend([s["begin_lon"], s["end_lon"]])
        if s.get("field_lat") is not None:
            lats.append(s["field_lat"])
            lons.append(s["field_lon"])
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)
    sites_json = json.dumps(sites, separators=(",", ":"))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    html, body {{ margin: 0; height: 100%; font-family: system-ui, sans-serif; }}
    #map {{ width: 100%; height: 100%; }}
    .hint {{
      position: absolute; top: 10px; left: 50px; right: 10px; z-index: 1000;
      background: rgba(255,255,255,0.94); padding: 10px 14px; border-radius: 8px;
      font-size: 13px; box-shadow: 0 2px 8px rgba(0,0,0,0.12); line-height: 1.45;
    }}
    .legend span {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%;
      margin-right: 4px; vertical-align: middle; border: 1px solid rgba(0,0,0,0.15); }}
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="hint">
    <b>{safe_title}</b> — {len(sites)} site(s). Click any point for status.<br>
    <span class="legend">
      <span style="background:{COLOR_BEGIN}"></span>Begin
      <span style="background:{COLOR_END}; margin-left:10px"></span>End
      <span style="background:{COLOR_FIELD}; margin-left:10px"></span>Installed GPS
    </span>
  </div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    var sites = {sites_json};
    var STATUS = {{installed: "Installed", skipped: "Skipped", pending: "Not completed"}};
    var map = L.map("map").setView([{center_lat:.6f}, {center_lon:.6f}], 11);
    L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
      maxZoom: 19, attribution: "&copy; OpenStreetMap"
    }}).addTo(map);
    var bounds = [];
    function popupHtml(s, pointLabel, lat, lng) {{
      var st = STATUS[s.status] || s.status;
      var lines = [
        "<b>Site " + s.site + "</b> — " + (s.street || ""),
        "<b>Status:</b> " + st,
        "<b>" + pointLabel + ":</b> " + lat.toFixed(6) + ", " + lng.toFixed(6)
      ];
      if (s.status === "installed" && s.field_lat != null) {{
        lines.push("<b>Field GPS:</b> " + s.field_lat.toFixed(6) + ", " + s.field_lon.toFixed(6));
      }}
      lines.push('<a target="_blank" rel="noopener" href="https://www.google.com/maps?q=' +
        lat + "," + lng + '">Google Maps</a>');
      return lines.join("<br>");
    }}
    function addPt(lat, lng, color, s, label) {{
      var m = L.circleMarker([lat, lng], {{
        radius: 8, color: color, fillColor: color, fillOpacity: 0.9, weight: 2
      }}).addTo(map);
      m.bindPopup(popupHtml(s, label, lat, lng));
      bounds.push([lat, lng]);
    }}
    sites.forEach(function(s) {{
      L.polyline([[s.begin_lat, s.begin_lon], [s.end_lat, s.end_lon]], {{
        color: "#78909c", weight: 2, opacity: 0.55, dashArray: "4 6"
      }}).addTo(map);
      addPt(s.begin_lat, s.begin_lon, "{COLOR_BEGIN}", s, "Begin");
      addPt(s.end_lat, s.end_lon, "{COLOR_END}", s, "End");
      if (s.status === "installed" && s.field_lat != null) {{
        addPt(s.field_lat, s.field_lon, "{COLOR_FIELD}", s, "Installed GPS");
      }}
    }});
    if (bounds.length) map.fitBounds(bounds, {{ padding: [48, 48] }});
  </script>
</body>
</html>
"""


def _empty_html(title: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{html_lib.escape(title)}</title></head>
<body><p>No sites to show on this map.</p></body></html>
"""


def _sites_from_est_only(est_path: Path) -> list[dict]:
    """Fallback when no shift stops — plan pin as begin/end, no status."""
    sites: list[dict] = []
    for p in pushpins_from_est(est_path):
        sites.append({
            "site": p["site"],
            "street": f"Site {p['site']}",
            "status": "pending",
            "begin_lat": round(p["lat"], 6),
            "begin_lon": round(p["lon"], 6),
            "end_lat": round(p["lat"], 6),
            "end_lon": round(p["lon"], 6),
        })
    return sites


def write_viewer_files(
    est_path: str | Path,
    *,
    base_path: str | Path | None = None,
    title: str = "",
    stops: list[dict] | None = None,
) -> dict[str, str]:
    """Write .html + .kml next to est. Pass stops for begin/end/installed/skipped."""
    est_path = Path(est_path)
    stem = Path(base_path) if base_path else est_path.with_suffix("")
    title = title or stem.name
    if stops:
        sites = sites_from_stops(stops)
    else:
        sites = _sites_from_est_only(est_path)
    html_path = Path(f"{stem}.html")
    kml_path = Path(f"{stem}.kml")
    html_path.write_text(to_html_map(sites, title=title), encoding="utf-8")
    kml_path.write_text(to_kml(sites, title=title), encoding="utf-8")
    return {"html": str(html_path), "kml": str(kml_path), "count": str(len(sites))}
