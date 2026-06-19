"""Google Maps navigation links for route stops (send to phone)."""
from __future__ import annotations

import html
import os
import re

from core.state import ca_now


def nav_coords(stop: dict) -> tuple[float, float] | None:
    """Drive-to point: road crossing if set, else site anchor."""
    clat, clon = stop.get("cross_lat"), stop.get("cross_lon")
    if clat is not None and clon is not None:
        return float(clat), float(clon)
    lat, lon = stop.get("lat"), stop.get("lon")
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    return None


def google_maps_nav_url(lat: float, lon: float) -> str:
    """Opens Google Maps driving directions to this point on phone or desktop."""
    return (
        f"https://www.google.com/maps/dir/?api=1"
        f"&destination={lat:.6f},{lon:.6f}&travelmode=driving"
    )


def _stop_label(stop: dict, seq: int) -> str:
    street = str(stop.get("street", "")).strip()
    if not street or street.lower() in ("nan", "none", "nat"):
        street = ""
    site = str(stop.get("id", "")).strip()
    if street and site:
        return f"{seq}. Site {site} — {street}"
    if site:
        return f"{seq}. Site {site}"
    if street:
        return f"{seq}. {street}"
    return f"{seq}. Stop"


def install_sequence_stops(stops: list[dict]) -> list[dict]:
    """All stops in route visit order (install driving sequence)."""
    return list(stops)


def pickup_sequence_stops(stops: list[dict]) -> list[dict]:
    """Installed stops sorted by install time (pickup reverse order)."""
    uid_order = {s["uid"]: i for i, s in enumerate(stops) if s.get("uid")}
    installed = [s for s in stops if s.get("installed")]
    installed.sort(
        key=lambda s: (
            str(s.get("exact_time") or s.get("date") or ""),
            uid_order.get(s.get("uid", ""), 10**9),
        )
    )
    return installed


def build_route_links(stops: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Return (links, errors) for stops in current visit order.
    Each link: {seq, id, street, lat, lon, label, url}.
    """
    if not stops:
        return [], ["No route stops yet — build your route first."]
    links: list[dict] = []
    errors: list[str] = []
    for i, stop in enumerate(stops, start=1):
        coords = nav_coords(stop)
        if not coords:
            errors.append(f"Stop {i} (site {stop.get('id', '?')}): missing coordinates")
            continue
        lat, lon = coords
        label = _stop_label(stop, i)
        links.append({
            "seq": i,
            "id": stop.get("id", ""),
            "street": stop.get("street", ""),
            "lat": lat,
            "lon": lon,
            "label": label,
            "url": google_maps_nav_url(lat, lon),
        })
    if not links and not errors:
        errors.append("No stops with GPS coordinates.")
    return links, errors


def to_plain_text(links: list[dict], *, profile: str = "") -> str:
    lines = ["Traffic Deployer — route stops (tap link on phone for Google Maps driving)"]
    if profile:
        lines.append(f"Profile: {profile}")
    lines.append("")
    for item in links:
        lines.append(item["label"])
        lines.append(item["url"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def batch_title(kind: str, profile: str) -> str:
    prof = f" — {profile}" if profile else ""
    if kind == "install":
        return f"Install route{prof}"
    if kind == "pickup":
        return f"Pickup (install order){prof}"
    return f"Route{prof}"


def to_html(
    links: list[dict],
    *,
    profile: str = "",
    miles: float | None = None,
    kind: str = "",
) -> str:
    title = batch_title(kind, profile) if kind else (f"Route — {profile}" if profile else "Route stops")
    meta_miles = f" · {miles:.1f} mi" if miles and miles > 0 else ""
    rows = []
    for item in links:
        safe_label = html.escape(item["label"])
        safe_url = html.escape(item["url"], quote=True)
        rows.append(f'    <a href="{safe_url}">{safe_label}</a>')
    body_links = "\n".join(rows) if rows else "    <p>No stops with coordinates.</p>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 0; padding: 16px; background: #f4f7fb; color: #0f2744; }}
    h1 {{ font-size: 1.25rem; margin: 0 0 4px; }}
    p.hint {{ color: #475569; font-size: 0.9rem; margin: 0 0 16px; }}
    a {{ display: block; padding: 14px 16px; margin: 10px 0; background: #1e88e5; color: #fff;
         text-decoration: none; border-radius: 10px; font-size: 1.05rem; font-weight: 600;
         box-shadow: 0 2px 6px rgba(15,39,68,0.12); }}
    a:active {{ background: #1565c0; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}{html.escape(meta_miles)}</h1>
  <p class="hint">Tap a stop — Google Maps opens driving directions. Send this file to your phone (text, email, AirDrop).</p>
{body_links}
</body>
</html>
"""


def _safe_profile(profile: str) -> str:
    return re.sub(r"[^\w\-]+", "_", (profile or "ROUTE").strip())[:40] or "ROUTE"


def default_links_path(
    data_dir: str,
    profile: str,
    *,
    kind: str = "",
    sheet: str = "",
) -> str:
    exports = os.path.join(data_dir, "exports")
    os.makedirs(exports, exist_ok=True)
    day, _ = ca_now()
    suffix = {"install": "_Install", "pickup": "_Pickup"}.get(kind, "")
    sheet_bit = f"_{_safe_profile(sheet)}" if sheet else ""
    name = f"TDS_Route_Links_{_safe_profile(profile)}{sheet_bit}{suffix}_{day}.html"
    return os.path.join(exports, name)


def write_pickup_links_page(
    stops: list[dict],
    path: str,
    *,
    profile: str = "",
    sheet: str = "",
) -> tuple[int, list[str]]:
    """Pickup sequence HTML for installed stops. Returns (link_count, errors)."""
    batch = pickup_sequence_stops(stops)
    links, errors = build_route_links(batch)
    body = to_html(links, profile=sheet or profile, kind="pickup")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return len(links), errors
