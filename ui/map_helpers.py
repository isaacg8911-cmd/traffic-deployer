"""Pure map/GPS helpers — P46 extract from MapSyncControllerMixin."""

from __future__ import annotations

import math


def dist_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = (lat2 - lat1) * 111320.0
    dlon = (lon2 - lon1) * 111320.0 * math.cos(math.radians(lat1))
    return (dlat * dlat + dlon * dlon) ** 0.5


def coords_moved(
    a: tuple[float, float],
    b: tuple[float, float],
    *,
    min_m: float = 4.0,
) -> bool:
    return dist_m(a[0], a[1], b[0], b[1]) >= min_m


def heading_cardinal(deg: float | None) -> str:
    if deg is None:
        return "—"
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[int(((deg + 22.5) % 360) / 45)]


def should_push_gps_bridge(
    lat: float,
    lon: float,
    heading: float | None,
    *,
    last: tuple[float, float, float | None] | None,
    last_t: float,
    now: float,
    heartbeat_s: float,
    min_m: float,
) -> bool:
    if last is None:
        return True
    if now - last_t >= heartbeat_s:
        return True
    llat, llon, lhdg = last
    if coords_moved((llat, llon), (lat, lon), min_m=min_m):
        return True
    if heading is not None and lhdg is not None:
        delta = abs(((heading - lhdg) + 180) % 360 - 180)
        if delta >= 12.0:
            return True
    return False


def display_route_for_map(route: dict | None) -> dict:
    """Map shows precomputed next leg only — not the full tour polyline."""
    r = route or {}
    return {
        "polyline": [],
        "miles": r.get("miles", 0.0),
        "graph": r.get("graph", False),
    }


def shift_has_field_progress(stops: list[dict]) -> bool:
    return any(
        s.get("installed") or s.get("skipped") or s.get("picked_up")
        for s in stops
    )
