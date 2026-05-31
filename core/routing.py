"""Route engine: order stops by the most efficient way to CROSS each street line.

Each site is a street segment (begin -> end). Routing ignores the midpoint;
it finds the best road approach to cross each segment line, orders segments to
minimize total drive miles, traces real streets home -> crossings -> home.
"""
from __future__ import annotations

import math

import road_router

try:
    import networkx as nx
    _HAS_NX = True
except Exception:
    _HAS_NX = False


def _haversine_km(a, b):
    R = 6371.0
    dlat = math.radians(b[0] - a[0])
    dlon = math.radians(b[1] - a[1])
    h = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def _seg_endpoints(s: dict) -> tuple[tuple[float, float], tuple[float, float]]:
    return ((float(s["begin_lat"]), float(s["begin_lon"])),
            (float(s["end_lat"]), float(s["end_lon"])))


def _project_on_segment(beg: tuple[float, float], end: tuple[float, float],
                        p: tuple[float, float]) -> tuple[float, float]:
    """Closest point on segment beg->end to p (lat, lon). Badge sits here."""
    dy = end[0] - beg[0]
    dx = end[1] - beg[1]
    py = p[0] - beg[0]
    px = p[1] - beg[1]
    seg2 = dx * dx + dy * dy
    if seg2 < 1e-18:
        return beg
    t = max(0.0, min(1.0, (px * dx + py * dy) / seg2))
    return (beg[0] + t * dy, beg[1] + t * dx)


def _segment_access(graph, stop: dict) -> dict:
    """Road attachment points at each end of the street segment line."""
    b, e = _seg_endpoints(stop)
    if graph is not None:
        return road_router.segment_access(graph, b, e)
    return {"begin": b, "end": e}


def _road_m(graph, a: tuple[float, float], b: tuple[float, float]) -> float:
    if graph is not None:
        return road_router.road_distance_m(graph, a, b)
    return _haversine_km(a, b) * 1000.0


def _access_pts(acc: dict) -> list[tuple[float, float]]:
    return [acc["begin"], acc["end"]]


def _pair_dist(graph, acc_a: dict, acc_b: dict) -> float:
    return min(_road_m(graph, p, q) for p in _access_pts(acc_a) for q in _access_pts(acc_b))


def _home_to_segment(graph, home: tuple[float, float], acc: dict) -> float:
    return min(_road_m(graph, home, p) for p in _access_pts(acc))


def _assign_crossings(graph, home: tuple[float, float], ordered: list[dict]) -> list[dict]:
    """Pick the cheapest end of each segment line to cross from the current road position."""
    cur = (float(home[0]), float(home[1]))
    for stop in ordered:
        acc = _segment_access(graph, stop)
        d_b = _road_m(graph, cur, acc["begin"])
        d_e = _road_m(graph, cur, acc["end"])
        seg_b, seg_e = _seg_endpoints(stop)
        if d_b <= d_e:
            attach = acc["begin"]
            stop["cross_side"] = "begin"
        else:
            attach = acc["end"]
            stop["cross_side"] = "end"
        cross = _project_on_segment(seg_b, seg_e, attach)
        stop["cross_lat"], stop["cross_lon"] = cross
        cur = attach
    return ordered


def _snap_leg_end(polyline: list, end: tuple[float, float]) -> list:
    """End the leg at the crossing on the site line (road touches, does not chase the stop)."""
    if not polyline:
        return [[end[0], end[1]]]
    out = list(polyline)
    out[-1] = [end[0], end[1]]
    return out


def _stop_pt(s: dict) -> tuple[float, float]:
    """Navigation target: field GPS if stamped, else optimal line crossing."""
    if s.get("field_lat") is not None and s.get("field_lon") is not None:
        return float(s["field_lat"]), float(s["field_lon"])
    if s.get("cross_lat") is not None and s.get("cross_lon") is not None:
        return float(s["cross_lat"]), float(s["cross_lon"])
    return float(s["lat"]), float(s["lon"])


def _use_fast_order_matrix(graph, n_stops: int) -> bool:
    """Full-graph Dijkstra ordering is minutes on large OSM extracts; haversine is seconds."""
    if graph is None:
        return True
    if n_stops > 12:
        return True
    try:
        return graph.number_of_nodes() > 8000
    except Exception:
        return True


def _haversine_matrix(home: tuple[float, float], stops: list[dict]) -> list[list[float]]:
    """Fast TSP matrix from straight-line distances (order only; route still uses real roads)."""
    accs = [_segment_access(None, s) for s in stops]
    n = len(stops) + 1
    m = [[0.0] * n for _ in range(n)]
    for j, acc in enumerate(accs, start=1):
        m[0][j] = m[j][0] = _home_to_segment(None, home, acc)
    for i, ai in enumerate(accs, start=1):
        for j, aj in enumerate(accs, start=1):
            if i != j:
                m[i][j] = _pair_dist(None, ai, aj)
    return m


def _road_matrix(graph, home: tuple[float, float], stops: list[dict]) -> list[list[float]]:
    """Distance matrix: index 0 = home, 1..n = segment line (min road dist between access ends)."""
    if graph is None or _use_fast_order_matrix(graph, len(stops)):
        return _haversine_matrix(home, stops)

    accs = [_segment_access(graph, s) for s in stops]
    n = len(stops) + 1
    m = [[0.0] * n for _ in range(n)]

    # Small graphs only: one Dijkstra per attachment node (large graphs hang for minutes).
    def _nodes_for_acc(acc: dict) -> list:
        nb = road_router.nearest_node(graph, acc["begin"][0], acc["begin"][1])
        ne = road_router.nearest_node(graph, acc["end"][0], acc["end"][1])
        return [nb, ne]

    home_n = road_router.nearest_node(graph, float(home[0]), float(home[1]))
    stop_nodes = [_nodes_for_acc(a) for a in accs]
    all_nodes = {home_n, *{nd for pair in stop_nodes for nd in pair}}

    lengths: dict = {}
    for src in all_nodes:
        try:
            lengths[src] = nx.single_source_dijkstra_path_length(graph, src, weight="length")
        except Exception:
            lengths[src] = {}

    def _node_dist(a, b) -> float:
        if a == b:
            return 0.0
        d = lengths.get(a, {}).get(b)
        if d is not None:
            return float(d)
        ya, xa = graph.nodes[a]["y"], graph.nodes[a]["x"]
        yb, xb = graph.nodes[b]["y"], graph.nodes[b]["x"]
        return _haversine_km((ya, xa), (yb, xb)) * 1000.0

    def _seg_dist(nodes_a: list, nodes_b: list) -> float:
        return min(_node_dist(u, v) for u in nodes_a for v in nodes_b)

    for j, nj in enumerate(stop_nodes, start=1):
        m[0][j] = m[j][0] = _seg_dist([home_n], nj)
    for i, ni in enumerate(stop_nodes, start=1):
        for j, nj in enumerate(stop_nodes, start=1):
            if i != j:
                m[i][j] = _seg_dist(ni, nj)
    return m


def _nearest_neighbor(matrix, start_idx, stop_indices):
    route, unvisited, cur = [], list(stop_indices), start_idx
    while unvisited:
        nxt = min(unvisited, key=lambda j: matrix[cur][j])
        route.append(nxt)
        unvisited.remove(nxt)
        cur = nxt
    return route


def _path_len(matrix, start_idx, route):
    if not route:
        return 0.0
    d = matrix[start_idx][route[0]]
    for a, b in zip(route, route[1:]):
        d += matrix[a][b]
    return d


def _two_opt(matrix, start_idx, route, max_passes=30):
    if len(route) < 4:
        return route
    best, best_d, improved, passes = list(route), _path_len(matrix, start_idx, route), True, 0
    while improved and passes < max_passes:
        improved, passes = False, passes + 1
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                if j - i == 1:
                    continue
                cand = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                cand_d = _path_len(matrix, start_idx, cand)
                if cand_d + 1e-6 < best_d:
                    best, best_d, improved = cand, cand_d, True
    return best


def optimize(stops: list[dict], home: tuple[float, float], data_dir: str) -> dict:
    """Order segments for minimum road miles to cross each street line."""
    if not stops:
        return {"order": [], "graph": False}

    graph = None
    if road_router.HAS_ROUTING and _HAS_NX and road_router.has_graph(data_dir):
        graph = road_router.load_graph(data_dir)

    matrix = _road_matrix(graph, home, stops)
    stop_indices = list(range(1, len(stops) + 1))
    route = _nearest_neighbor(matrix, 0, stop_indices)
    if len(route) <= 80:
        route = _two_opt(matrix, 0, route, max_passes=12 if len(route) > 35 else 30)

    ordered = [stops[i - 1] for i in route]
    ordered = _assign_crossings(graph, home, ordered)
    return {"order": ordered, "graph": graph is not None}


def build_route(ordered_stops: list[dict], home: tuple[float, float], data_dir: str) -> dict:
    """Real road polyline tracing home -> each line crossing -> home."""
    if not ordered_stops:
        return {"polyline": [], "miles": 0.0, "legs": [], "graph": False}

    ordered = _assign_crossings(
        road_router.load_graph(data_dir) if road_router.has_graph(data_dir) else None,
        home, list(ordered_stops))
    try:
        from core import street_intel
        street_intel.annotate_stops(ordered, data_dir)
    except Exception:
        pass

    if road_router.HAS_ROUTING and road_router.has_graph(data_dir):
        graph = road_router.load_graph(data_dir)
        if graph is not None:
            targets = [(*_stop_pt(s), f"Site {s['id']}") for s in ordered]
            legs = road_router.directions_for_stops(graph, home, targets)
            # Return leg: last crossing back to home.
            last = _stop_pt(ordered[-1])
            ret = road_router.route_between(graph, last, home)
            ret["from"] = f"Stop {len(ordered)}"
            ret["to"] = "Home"
            legs.append(ret)
            polyline, miles = [], 0.0
            for i, leg in enumerate(legs):
                coords = leg.get("polyline") or []
                if i < len(ordered):
                    touch = _stop_pt(ordered[i])
                    coords = _snap_leg_end(coords, touch)
                    leg["polyline"] = coords
                if coords:
                    if polyline and polyline[-1] == coords[0]:
                        polyline.extend(coords[1:])
                    else:
                        polyline.extend(coords)
                if leg.get("ok"):
                    miles += leg.get("miles", 0.0)
            return {"polyline": polyline, "miles": miles, "legs": legs, "graph": True}

    pts = [(float(home[0]), float(home[1]))] + [_stop_pt(s) for s in ordered] + [(float(home[0]), float(home[1]))]
    polyline = [[p[0], p[1]] for p in pts]
    miles = sum(_haversine_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) * 0.621371
    return {"polyline": polyline, "miles": miles, "legs": [], "graph": False}
