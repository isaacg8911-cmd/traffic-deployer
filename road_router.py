"""
Offline road routing + turn-by-turn directions for Traffic Deployer.

Uses OpenStreetMap road data via osmnx:
- download_area(...)  -> run ONCE with wifi (at home): builds + saves a road graph
                         covering your stops, into tds_data/road_graph.graphml
- load_graph(...)     -> loads the saved graph (works fully OFFLINE)
- directions_for_stops(...) -> Google-Maps-style turn-by-turn for an ordered route

No scikit-learn, no Docker. Degrades safely if osmnx is unavailable.
"""
from __future__ import annotations

import math
import os

import numpy as np

try:
    import osmnx as ox
    import networkx as nx
    HAS_ROUTING = True
except Exception:
    HAS_ROUTING = False

GRAPH_FILENAME = "road_graph.graphml"
_GRAPH_CACHE: dict = {}
_NODE_ARRAYS: dict = {}


def graph_path(data_dir: str) -> str:
    return os.path.join(data_dir, GRAPH_FILENAME)


def has_graph(data_dir: str) -> bool:
    return os.path.exists(graph_path(data_dir))


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def download_area(points, data_dir: str, buffer_m: float = 1500, network_type: str = "drive") -> dict:
    """Build + save a drive graph covering all points (lat,lon). Requires internet.

    Uses the TIGHT bounding box of the points (+ a small buffer) instead of a big
    circle around the centroid. For spread-out routes this downloads far less data
    and finishes much faster.
    """
    if not HAS_ROUTING:
        raise RuntimeError("Routing libraries (osmnx) are not installed.")
    pts = [(float(p[0]), float(p[1])) for p in points if p and p[0] and p[1]]
    if not pts:
        raise ValueError("No valid points to cover.")

    # Give Overpass a real, bounded timeout so a slow query fails loudly instead
    # of hanging the UI forever.
    for attr in ("requests_timeout", "timeout"):
        try:
            setattr(ox.settings, attr, 300)
        except Exception:
            pass

    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    mlat = (min(lats) + max(lats)) / 2.0
    dlat = buffer_m / 111320.0
    dlon = buffer_m / (111320.0 * max(math.cos(math.radians(mlat)), 0.1))
    north, south = max(lats) + dlat, min(lats) - dlat
    east, west = max(lons) + dlon, min(lons) - dlon

    os.makedirs(data_dir, exist_ok=True)
    import sys
    print(f"[road download] bbox west={west:.4f} south={south:.4f} east={east:.4f} north={north:.4f}", flush=True)
    G = ox.graph_from_bbox(bbox=(west, south, east, north), network_type=network_type, simplify=True)
    named = 0
    for _u, _v, _k, d in G.edges(keys=True, data=True):
        nm = d.get("name")
        if nm and (not isinstance(nm, list) or nm[0]):
            named += 1
    print(f"[road download] got {len(G.nodes)} nodes, {named} named edges, saving...", flush=True)
    ox.save_graphml(G, graph_path(data_dir))
    _GRAPH_CACHE[data_dir] = G
    _NODE_ARRAYS.pop(id(G), None)
    span_mi = _haversine_m(south, west, north, east) / 1609.34
    return {
        "nodes": len(G.nodes),
        "edges": len(G.edges),
        "named_edges": named,
        "radius_mi": round(span_mi, 1),
    }


def load_graph(data_dir: str):
    """Load the cached graph (offline). Returns None if not downloaded yet."""
    if not HAS_ROUTING:
        return None
    if data_dir in _GRAPH_CACHE:
        return _GRAPH_CACHE[data_dir]
    if not has_graph(data_dir):
        return None
    G = ox.load_graphml(graph_path(data_dir))
    _GRAPH_CACHE[data_dir] = G
    return G


def _node_arrays(G):
    key = id(G)
    if key not in _NODE_ARRAYS:
        ids = list(G.nodes)
        ys = np.array([G.nodes[n]["y"] for n in ids])
        xs = np.array([G.nodes[n]["x"] for n in ids])
        _NODE_ARRAYS[key] = (ids, ys, xs)
    return _NODE_ARRAYS[key]


def nearest_node(G, lat, lon):
    ids, ys, xs = _node_arrays(G)
    dlat = np.radians(ys - lat)
    dlon = np.radians(xs - lon)
    a = np.sin(dlat / 2) ** 2 + np.cos(np.radians(lat)) * np.cos(np.radians(ys)) * np.sin(dlon / 2) ** 2
    d = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return ids[int(np.argmin(d))]


def _edge_name(data: dict) -> str:
    name = data.get("name") or data.get("ref") or ""
    if isinstance(name, list):
        name = name[0] if name else ""
    return str(name).strip()


def _street_name(G, u, v):
    data = G.get_edge_data(u, v)
    if not data:
        return "road"
    d = data[min(data.keys())]
    name = _edge_name(d)
    return name or "road"


def street_name_at(data_dir: str, lat: float, lon: float) -> str:
    """Nearest OSM road name from the saved graph (fully offline)."""
    if not (HAS_ROUTING and has_graph(data_dir)):
        return ""
    G = load_graph(data_dir)
    if G is None:
        return ""
    try:
        import osmnx as ox
        u, v, key = ox.nearest_edges(G, float(lon), float(lat))
        return _edge_name(G[u][v][key])
    except Exception:
        return ""


def _bearing(a, b):
    return ox.bearing.calculate_bearing(a[0], a[1], b[0], b[1])


def turn_by_turn(G, route) -> list[str]:
    """Build a turn-by-turn list from a node route."""
    if len(route) < 2:
        return ["Arrive at destination"]
    coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in route]
    steps: list[str] = []
    cur_street = None
    seg_dist = 0.0
    compass8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

    for i in range(len(route) - 1):
        name = _street_name(G, route[i], route[i + 1])
        leg_m = _haversine_m(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])

        if cur_street is None:
            b = _bearing(coords[i], coords[i + 1])
            steps.append(f"Head {compass8[int(((b + 22.5) % 360) / 45)]} on {name}")
            cur_street = name
            seg_dist = leg_m
        elif name != cur_street:
            in_b = _bearing(coords[i - 1], coords[i]) if i > 0 else _bearing(coords[i], coords[i + 1])
            out_b = _bearing(coords[i], coords[i + 1])
            angle = ((out_b - in_b + 180) % 360) - 180
            if abs(angle) < 25:
                direction = "Continue"
            elif angle >= 150 or angle <= -150:
                direction = "Make a U-turn"
            elif angle > 0:
                direction = "Turn right"
            else:
                direction = "Turn left"
            steps.append(f"In {seg_dist * 3.281:.0f} ft, {direction} onto {name}")
            cur_street = name
            seg_dist = leg_m
        else:
            seg_dist += leg_m

    steps.append(f"In {seg_dist * 3.281:.0f} ft, arrive at destination")
    return steps


def route_between(G, a, b) -> dict:
    """a, b = (lat, lon). Returns {ok, miles, steps, polyline}."""
    try:
        on = nearest_node(G, a[0], a[1])
        dn = nearest_node(G, b[0], b[1])
        route = nx.shortest_path(G, on, dn, weight="length")
        dist = nx.shortest_path_length(G, on, dn, weight="length")
        coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in route]
        return {"ok": True, "miles": dist / 1609.34, "steps": turn_by_turn(G, route), "polyline": coords}
    except Exception as exc:
        return {"ok": False, "miles": 0.0, "steps": [f"No road route found ({exc})"], "polyline": [a, b]}


def _classify_turn(angle: float) -> str:
    if abs(angle) < 25:
        return "straight"
    if angle >= 150 or angle <= -150:
        return "uturn"
    return "right" if angle > 0 else "left"


def _maneuvers_on_route(G, route, *, stop_index: int | None = None) -> list[dict]:
    """Turn-by-turn maneuvers for one graph node route."""
    if len(route) < 2:
        if stop_index is not None:
            n = route[0]
            return [{"type": "arrive", "street": "", "lat": G.nodes[n]["y"], "lon": G.nodes[n]["x"],
                     "dist_m": 0.0, "stop_index": stop_index}]
        return []

    coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in route]
    maneuvers: list[dict] = []
    cur_street = None
    for i in range(len(route) - 1):
        name = _street_name(G, route[i], route[i + 1])
        seg = _haversine_m(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
        if cur_street is None:
            maneuvers.append({"type": "depart", "street": name,
                              "lat": coords[i][0], "lon": coords[i][1],
                              "dist_m": seg, "stop_index": None})
            cur_street = name
        elif name != cur_street:
            in_b = _bearing(coords[i - 1], coords[i]) if i > 0 else _bearing(coords[i], coords[i + 1])
            out_b = _bearing(coords[i], coords[i + 1])
            angle = ((out_b - in_b + 180) % 360) - 180
            maneuvers.append({"type": _classify_turn(angle), "street": name,
                              "lat": coords[i][0], "lon": coords[i][1],
                              "dist_m": seg, "stop_index": None})
            cur_street = name
        elif maneuvers:
            maneuvers[-1]["dist_m"] += seg

    if stop_index is not None:
        maneuvers.append({"type": "arrive", "street": "",
                          "lat": coords[-1][0], "lon": coords[-1][1],
                          "dist_m": 0.0, "stop_index": stop_index})
    return maneuvers


def leg_plan(G, a, b, stop_index: int = 0) -> dict:
    """Single-leg structured plan + polyline. Fast enough for live offline reroute."""
    a = (float(a[0]), float(a[1]))
    b = (float(b[0]), float(b[1]))
    try:
        on = nearest_node(G, a[0], a[1])
        dn = nearest_node(G, b[0], b[1])
        route = nx.shortest_path(G, on, dn, weight="length")
        coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in route]
        polyline = [[float(c[0]), float(c[1])] for c in coords]
        if len(route) < 2:
            name = ""
            try:
                import osmnx as ox
                u, v, key = ox.nearest_edges(G, float(a[1]), float(a[0]))
                name = _edge_name(G[u][v][key])
            except Exception:
                name = ""
            dist = _haversine_m(a[0], a[1], b[0], b[1])
            maneuvers = [
                {"type": "depart", "street": name or "road", "lat": a[0], "lon": a[1],
                 "dist_m": dist, "stop_index": None},
                {"type": "arrive", "street": "", "lat": b[0], "lon": b[1],
                 "dist_m": 0.0, "stop_index": stop_index},
            ]
            if len(polyline) < 2:
                polyline = [[a[0], a[1]], [b[0], b[1]]]
        else:
            maneuvers = _maneuvers_on_route(G, route, stop_index=stop_index)
        return {"ok": True, "maneuvers": maneuvers, "polyline": polyline}
    except Exception:
        return {
            "ok": False,
            "maneuvers": [{"type": "arrive", "street": "", "lat": b[0], "lon": b[1],
                           "dist_m": 0.0, "stop_index": stop_index}],
            "polyline": [[a[0], a[1]], [b[0], b[1]]],
        }


def dist_to_polyline_m(lat: float, lon: float, poly: list) -> float:
    """Minimum distance (m) from a point to a lat/lon polyline."""
    if not poly or len(poly) < 2:
        return 1e18
    best = 1e18
    px, py = float(lon), float(lat)
    for i in range(len(poly) - 1):
        y1, x1 = float(poly[i][0]), float(poly[i][1])
        y2, x2 = float(poly[i + 1][0]), float(poly[i + 1][1])
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            d = _haversine_m(lat, lon, y1, x1)
        else:
            t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
            # Approximate local projection (good enough for off-route detection).
            lat_m = 111320.0
            lon_m = 111320.0 * max(math.cos(math.radians(lat)), 0.1)
            qx, qy = x1 + t * dx, y1 + t * dy
            dlat = (qy - lat) * lat_m
            dlon = (qx - lon) * lon_m
            d = (dlat * dlat + dlon * dlon) ** 0.5
        best = min(best, d)
    return best


def nav_plan_light(G, pts) -> dict:
    """Fast turn-by-turn: one leg per stop (no per-street expansion). Used while driving."""
    maneuvers: list[dict] = []
    full_poly: list[list[float]] = []
    legs: list[list[list[float]]] = []
    total_m = 0.0
    for li in range(len(pts) - 1):
        a, b = pts[li], pts[li + 1]
        leg = route_between(G, a, b)
        coords = leg.get("polyline") or [a, b]
        leg_pts = [[float(c[0]), float(c[1])] for c in coords]
        legs.append(leg_pts)
        if leg_pts:
            if full_poly and full_poly[-1] == leg_pts[0]:
                full_poly.extend(leg_pts[1:])
            else:
                full_poly.extend(leg_pts)
        if leg.get("ok"):
            total_m += leg.get("miles", 0.0) * 1609.34
        name = ""
        if len(coords) >= 2:
            try:
                on = nearest_node(G, coords[0][0], coords[0][1])
                dn = nearest_node(G, coords[1][0], coords[1][1])
                name = _street_name(G, on, dn)
            except Exception:
                name = ""
        maneuvers.append({"type": "depart", "street": name or "road",
                          "lat": coords[0][0], "lon": coords[0][1],
                          "dist_m": 0.0, "stop_index": None})
        maneuvers.append({"type": "arrive", "street": "",
                          "lat": b[0], "lon": b[1],
                          "dist_m": 0.0, "stop_index": max(0, li)})
    return {"plan": maneuvers, "polyline": full_poly, "legs": legs, "miles": total_m / 1609.34}


def nav_plan(G, pts, labels=None) -> dict:
    """Structured turn-by-turn plan across an ordered list of points.

    pts = [start, stop0, stop1, ...] as (lat, lon).
    Returns {plan, polyline, legs, miles} where plan is a list of maneuvers:
        {type, street, lat, lon, dist_m, stop_index}
      - type: depart | straight | left | right | uturn | arrive
      - dist_m: meters travelled on this maneuver's street until the next maneuver
      - stop_index: set on 'arrive' maneuvers (index into the stops list), else None
    Designed so the app can track position cheaply (no Dijkstra) while driving.
    """
    maneuvers: list[dict] = []
    full_poly: list[list[float]] = []
    legs: list[list[list[float]]] = []
    total_m = 0.0

    for li in range(len(pts) - 1):
        a, b = pts[li], pts[li + 1]
        leg = leg_plan(G, a, b, stop_index=max(0, li))
        leg_pts = leg.get("polyline") or [[a[0], a[1]], [b[0], b[1]]]
        legs.append(leg_pts)
        if leg_pts:
            if full_poly and full_poly[-1] == leg_pts[0]:
                full_poly.extend(leg_pts[1:])
            else:
                full_poly.extend(leg_pts)
        for m in leg.get("maneuvers") or []:
            if m["type"] != "arrive" or m.get("stop_index") is not None:
                total_m += float(m.get("dist_m") or 0.0)
            maneuvers.extend(leg.get("maneuvers") or [])

    return {"plan": maneuvers, "polyline": full_poly, "legs": legs, "miles": total_m / 1609.34}


def segment_access(G, begin: tuple[float, float], end: tuple[float, float]) -> dict:
    """Road-network attachment points at each end of a street segment line."""
    nb = nearest_node(G, begin[0], begin[1])
    ne = nearest_node(G, end[0], end[1])
    return {
        "begin": (G.nodes[nb]["y"], G.nodes[nb]["x"]),
        "end": (G.nodes[ne]["y"], G.nodes[ne]["x"]),
    }


def road_distance_m(G, a: tuple[float, float], b: tuple[float, float]) -> float:
    """Shortest drive distance in meters between two lat/lon points on the graph."""
    try:
        na = nearest_node(G, a[0], a[1])
        nb = nearest_node(G, b[0], b[1])
        return nx.shortest_path_length(G, na, nb, weight="length")
    except Exception:
        return _haversine_m(a[0], a[1], b[0], b[1])


def directions_for_stops(G, home, stops) -> list[dict]:
    """
    home = (lat, lon); stops = list of (lat, lon, label).
    Returns one leg dict per hop (Start->stop1->stop2->...), each with from/to/miles/steps/polyline.
    """
    pts = [(float(home[0]), float(home[1]))] + [(float(s[0]), float(s[1])) for s in stops]
    labels = ["Start"] + [str(s[2]) for s in stops]
    legs = []
    for i in range(len(pts) - 1):
        leg = route_between(G, pts[i], pts[i + 1])
        leg["from"] = labels[i]
        leg["to"] = labels[i + 1]
        legs.append(leg)
    return legs
