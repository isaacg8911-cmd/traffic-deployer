"""Offline street width / lane checks using the saved OSM road graph."""
from __future__ import annotations

import math
import re

import road_router

# Highways we treat as too wide for typical counter installs.
_WIDE_CLASSES = frozenset({
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link",
})
# At or above this lane count -> warn (4-lane+ arterials / boulevards).
_LANE_WARN = 4
# OSM width tag in meters (approx 4 normal lanes ~ 12–14 m).
_WIDTH_WARN_M = 14.0


def _parse_lanes(raw) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is None:
        return None
    nums = [int(x) for x in re.findall(r"\d+", str(raw))]
    return max(nums) if nums else None


def _parse_width_m(raw) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is None:
        return None
    s = str(raw).strip().lower().replace(",", ".")
    m = re.match(r"^([\d.]+)\s*(m|meter|metre|ft|feet)?", s)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "m").lower()
    if unit in ("ft", "feet"):
        val *= 0.3048
    return val


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _edges_near(graph, lat: float, lon: float, radius_m: float = 45.0) -> list[dict]:
    """Nearest OSM edge tags at a point (fast — no full neighborhood crawl)."""
    try:
        import osmnx as ox
    except Exception:
        return []
    try:
        u, v, key = ox.nearest_edges(graph, lon, lat)
        return [graph[u][v][key]]
    except Exception:
        node = road_router.nearest_node(graph, lat, lon)
        out: list[dict] = []
        for _u, _v, _k, data in graph.edges(node, keys=True, data=True):
            out.append(data)
            if len(out) >= 4:
                break
        return out


def analyze_point(graph, lat: float, lon: float) -> dict:
    """Return {wide, lanes, highway, width_m, message} for one location."""
    if graph is None:
        return {"wide": False, "lanes": None, "highway": None, "width_m": None, "message": ""}
    edges = _edges_near(graph, lat, lon)
    if not edges:
        return {"wide": False, "lanes": None, "highway": None, "width_m": None, "message": ""}

    max_lanes = None
    max_width = None
    hwys: set[str] = set()
    for data in edges:
        hw = data.get("highway")
        if isinstance(hw, list):
            hw = hw[0] if hw else None
        if hw:
            hwys.add(str(hw))
        ln = _parse_lanes(data.get("lanes"))
        if ln is not None:
            max_lanes = ln if max_lanes is None else max(max_lanes, ln)
        w = _parse_width_m(data.get("width"))
        if w is not None:
            max_width = w if max_width is None else max(max_width, w)

    reasons: list[str] = []
    if max_lanes is not None and max_lanes >= _LANE_WARN:
        reasons.append(f"{max_lanes} lanes")
    if max_width is not None and max_width >= _WIDTH_WARN_M:
        reasons.append(f"~{max_width:.0f} m wide")
    wide_hwy = sorted(hwys & _WIDE_CLASSES)
    if wide_hwy:
        reasons.append(wide_hwy[0].replace("_", " "))

    wide = bool(reasons)
    msg = ""
    if wide:
        msg = "WIDE STREET — " + ", ".join(reasons) + " (check before install)"
    return {
        "wide": wide,
        "lanes": max_lanes,
        "highway": wide_hwy[0] if wide_hwy else (next(iter(hwys), None)),
        "width_m": max_width,
        "message": msg,
    }


def analyze_segment(graph, begin: tuple[float, float], end: tuple[float, float],
                    cross: tuple[float, float] | None = None) -> dict:
    """Check begin, end, and optional crossing against nearby OSM edges."""
    if graph is None:
        return {"wide": False, "message": ""}
    pts = [begin, end]
    if cross:
        pts.append(cross)
    worst = {"wide": False, "lanes": None, "message": ""}
    for lat, lon in pts:
        r = analyze_point(graph, lat, lon)
        if r.get("wide"):
            if not worst["wide"] or (r.get("lanes") or 0) > (worst.get("lanes") or 0):
                worst = r
    return worst


def annotate_stops(stops: list[dict], data_dir: str) -> None:
    """Set street_warning on each stop when the road graph flags a wide arterial."""
    if not (road_router.HAS_ROUTING and road_router.has_graph(data_dir)):
        for s in stops:
            s["street_warning"] = ""
        return
    if len(stops) > 50:
        for s in stops:
            s.setdefault("street_warning", "")
        return
    graph = road_router.load_graph(data_dir)
    for s in stops:
        cross = None
        if s.get("cross_lat") is not None:
            cross = (float(s["cross_lat"]), float(s["cross_lon"]))
        r = analyze_segment(
            graph,
            (float(s["begin_lat"]), float(s["begin_lon"])),
            (float(s["end_lat"]), float(s["end_lon"])),
            cross,
        )
        s["street_warning"] = r.get("message") or ""
