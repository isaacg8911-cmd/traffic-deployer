"""Route engine: suggest stop order site 1 -> site N (open path, no return leg).

Each site is a street segment (begin -> end). The engine clusters nearby sites
into zones, orders zones outward from your start (GPS fix when available, else
setup origin), and minimizes road miles between crossings inside each zone.

You drive to site 1 yourself; legs chain site 1..N only. Full pipeline:
ROUTING_AND_MAP.md in the project root.
"""
from __future__ import annotations

import copy
import itertools
import math

import road_router
from core import time_est

try:
    import networkx as nx
    _HAS_NX = True
except Exception:
    _HAS_NX = False

# Field jobs never exceed this; batched road matrix + matrix 2-opt scale to here.
MAX_ORDER_STOPS = 100
# Exact matrix TSP for small jobs (proven best order on the road-distance matrix).
EXACT_MATRIX_MAX_STOPS = 9
# Optional OR-Tools TSP when installed (pip install ortools); used for 10–15 stops.
ORTOOLS_MATRIX_MAX_STOPS = 15
# Zone sweep: cluster geographically for 12+ stops (P20/P21).
ZONE_MIN_STOPS = 12
# Sample points between Excel begin/end when the chord is a real block.
# Skip pins (<40 m) and bogus multi-mile Excel pairs (>1.5 mi).
HOSE_INTERIOR_MIN_M = 40.0
HOSE_INTERIOR_MAX_M = 2400.0


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


def graph_covers_stops(graph, stops: list[dict], *, min_frac: float = 0.6) -> bool:
    """True only if the loaded road graph actually spans this job's sites.

    Guards the #1 silent failure: a road map downloaded for one area (e.g. home)
    but a job 100 mi away. Without this, nearest_node snaps every site to the same
    graph edge, all stop-to-stop distances collapse to ~0, and the optimizer emits a
    nonsense order with a tiny bogus mileage and zero failed legs.
    """
    if graph is None or not stops:
        return False
    inside = 0
    total = 0
    for s in stops:
        for p in _seg_endpoints(s):
            total += 1
            if road_router.covers_point(graph, p[0], p[1]):
                inside += 1
    if total == 0:
        return False
    return inside >= max(1, int(total * min_frac))


def _covering_graph(data_dir: str, stops: list[dict]):
    """Load the saved graph, but only return it when it covers the job.

    Returns (graph_or_None, uncovered) where uncovered is True when a graph exists
    on disk but does not span these sites — caller should route straight-line and
    tell the operator to download the road map for this job area.
    """
    if not (road_router.HAS_ROUTING and _HAS_NX and road_router.has_graph(data_dir)):
        return None, False
    graph = road_router.load_graph(data_dir)
    if graph is None:
        return None, False
    if graph_covers_stops(graph, stops):
        return graph, False
    return None, True


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


def _lerp_ll(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def _hose_len_m(stop: dict) -> float:
    b, e = _seg_endpoints(stop)
    return _haversine_km(b, e) * 1000.0


def _side_from_t(t: float) -> str:
    if t <= 0.12:
        return "begin"
    if t >= 0.88:
        return "end"
    return "mid"


def _sample_side(name: str) -> str:
    return name if name in ("begin", "end") else "mid"


def _seg_samples(stop: dict) -> list[tuple[str, tuple[float, float]]]:
    """Begin, end, and interior samples when the Excel chord is a usable block."""
    b, e = _seg_endpoints(stop)
    out: list[tuple[str, tuple[float, float]]] = [("begin", b), ("end", e)]
    meters = _hose_len_m(stop)
    if meters < HOSE_INTERIOR_MIN_M or meters > HOSE_INTERIOR_MAX_M:
        return out
    for t, name in ((0.25, "q1"), (0.5, "mid"), (0.75, "q3")):
        out.append((name, _lerp_ll(b, e, t)))
    return out


def _seg_candidates(stop: dict) -> list[tuple[float, float, str]]:
    """Drive-to options: endpoints plus on-line samples (unique coords)."""
    seen: set[tuple[float, float]] = set()
    out: list[tuple[float, float, str]] = []
    for name, pt in _seg_samples(stop):
        key = (round(pt[0], 6), round(pt[1], 6))
        if key in seen:
            continue
        seen.add(key)
        out.append((pt[0], pt[1], _sample_side(name)))
    return out


def _snap_ll(graph, pt: tuple[float, float]) -> tuple[float, float]:
    n = road_router.nearest_node(graph, pt[0], pt[1])
    return (float(graph.nodes[n]["y"]), float(graph.nodes[n]["x"]))


def _segment_access(graph, stop: dict) -> dict:
    """Road attachment points along the street segment (ends + interior)."""
    acc: dict[str, tuple[float, float]] = {}
    for name, pt in _seg_samples(stop):
        acc[name] = _snap_ll(graph, pt) if graph is not None else pt
    return acc


def _access_nodes(graph, acc: dict) -> list:
    nodes = []
    seen: set = set()
    for pt in _access_pts(acc):
        n = road_router.nearest_node(graph, pt[0], pt[1])
        if n not in seen:
            seen.add(n)
            nodes.append(n)
    return nodes


def _road_m(graph, a: tuple[float, float], b: tuple[float, float]) -> float:
    if graph is not None:
        return road_router.road_distance_m(graph, a, b)
    return _haversine_km(a, b) * 1000.0


def _cached_dist(graph, lengths: dict | None, a: tuple[float, float], b: tuple[float, float]) -> float:
    if graph is None:
        return _haversine_km(a, b) * 1000.0
    if lengths is not None:
        return road_router.distance_from_lengths(graph, lengths, a, b)
    return _road_m(graph, a, b)


def _access_pts(acc: dict) -> list[tuple[float, float]]:
    return list(acc.values())


def _pair_dist(graph, acc_a: dict, acc_b: dict) -> float:
    return min(_road_m(graph, p, q) for p in _access_pts(acc_a) for q in _access_pts(acc_b))


def _home_to_segment(graph, home: tuple[float, float], acc: dict) -> float:
    return min(_road_m(graph, home, p) for p in _access_pts(acc))


def _cross_begin_or_end(
    graph,
    lengths: dict | None,
    cur: tuple[float, float],
    stop: dict,
) -> tuple[float, float, str]:
    """Drive-to point on the site line: begin, end, or a closer point between them."""
    best: tuple[float, float, str] | None = None
    best_d = float("inf")
    for lat, lon, side in _seg_candidates(stop):
        d = _cached_dist(graph, lengths, cur, (lat, lon))
        if d < best_d:
            best_d = d
            best = (lat, lon, side)
    if best is None:
        b, _e = _seg_endpoints(stop)
        return b[0], b[1], "begin"
    return best


def _locked_cross(stop: dict, side: str) -> tuple[float, float, str]:
    """Drive-to point when the operator locked begin or end during manual pick."""
    seg_b, seg_e = _seg_endpoints(stop)
    if side == "begin":
        return seg_b[0], seg_b[1], "begin"
    return seg_e[0], seg_e[1], "end"


def _assign_crossings(
    graph,
    home: tuple[float, float],
    ordered: list[dict],
    lengths: dict | None = None,
) -> list[dict]:
    """Chain crossings using the closest point on each site line."""
    cur = (float(home[0]), float(home[1]))
    for stop in ordered:
        locked = stop.get("cross_side") if stop.get("pick_cross_locked") else None
        if locked in ("begin", "end"):
            lat, lon, side = _locked_cross(stop, locked)
        else:
            lat, lon, side = _cross_begin_or_end(graph, lengths, cur, stop)
        stop["cross_lat"], stop["cross_lon"] = lat, lon
        stop["cross_side"] = side
        cur = (lat, lon)
    return _slide_crossings(graph, ordered, lengths, home=home)


def _tour_cost_assigned(
    graph,
    home: tuple[float, float],
    assigned: list[dict],
    lengths: dict | None,
) -> float:
    """Drive miles along stops that already have crossings assigned."""
    if not assigned:
        return 0.0
    cur = (float(home[0]), float(home[1]))
    total = 0.0
    for s in assigned:
        nxt = _stop_pt(s)
        total += _cached_dist(graph, lengths, cur, nxt)
        cur = nxt
    total += _cached_dist(graph, lengths, cur, (float(home[0]), float(home[1])))
    return total / 1609.34


def _tour_cost_cached(
    graph,
    home: tuple[float, float],
    ordered: list[dict],
    lengths: dict | None,
) -> float:
    """Drive meters home -> crossings -> home using cached graph distances."""
    if not ordered:
        return 0.0
    trial = _assign_crossings(graph, home, copy.deepcopy(ordered), lengths=lengths)
    return _tour_cost_assigned(graph, home, trial, lengths)


def _refine_tour_2opt_cached(
    graph,
    home: tuple[float, float],
    ordered: list[dict],
    lengths: dict | None,
    *,
    max_passes: int = 12,
) -> list[dict]:
    """Improve visit order using true crossing tour cost (cached — no per-swap Dijkstra)."""
    if graph is None or lengths is None or len(ordered) < 3:
        return _assign_crossings(graph, home, ordered, lengths=lengths)
    best = copy.deepcopy(ordered)
    best_d = _tour_cost_cached(graph, home, best, lengths)
    improved, passes = True, 0
    while improved and passes < max_passes:
        improved, passes = False, passes + 1
        n = len(best)
        for i in range(n - 1):
            for j in range(i + 1, n):
                if j - i == 1:
                    continue
                cand = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                trial = _assign_crossings(
                    graph, home, copy.deepcopy(cand), lengths=lengths)
                d = _tour_cost_assigned(graph, home, trial, lengths)
                if d + 1e-4 < best_d:
                    best, best_d, improved = cand, d, True
    return _assign_crossings(graph, home, best, lengths=lengths)


def _polish_crossings(
    graph,
    home: tuple[float, float],
    ordered: list[dict],
    lengths: dict | None,
    *,
    max_rounds: int = 2,
) -> list[dict]:
    """Try flipping begin/end crossing per stop; re-chain greedy crossings after each flip."""
    if graph is None or lengths is None or len(ordered) < 2:
        return _assign_crossings(graph, home, ordered, lengths=lengths)
    best = _assign_crossings(graph, home, copy.deepcopy(ordered), lengths=lengths)
    best_d = _tour_cost_assigned(graph, home, best, lengths)
    for _round in range(max_rounds):
        improved = False
        for i in range(len(best)):
            trial = copy.deepcopy(best)
            stop = trial[i]
            stop["cross_side"] = "end" if stop.get("cross_side") == "begin" else "begin"
            seg_b, seg_e = _seg_endpoints(stop)
            prev = (float(home[0]), float(home[1])) if i == 0 else _stop_pt(trial[i - 1])
            lat, lon, side = _cross_begin_or_end(graph, lengths, prev, stop)
            stop["cross_lat"], stop["cross_lon"] = lat, lon
            stop["cross_side"] = side
            tail = _assign_crossings(graph, home, trial[i:], lengths=lengths)
            for k, s in enumerate(tail):
                trial[i + k] = s
            d = _tour_cost_assigned(graph, home, trial, lengths)
            if d + 1e-4 < best_d:
                best, best_d, improved = trial, d, True
        if not improved:
            break
    return best


def _same_coord(a: list | tuple, b: list | tuple, tol: float = 1e-6) -> bool:
    return abs(float(a[0]) - float(b[0])) < tol and abs(float(a[1]) - float(b[1])) < tol


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


def _haversine_matrix(
    home: tuple[float, float],
    stops: list[dict],
    graph=None,
) -> tuple[list[list[float]], dict | None]:
    """TSP matrix when no graph — straight-line / per-pair road snap."""
    accs = [_segment_access(graph, s) for s in stops]
    n = len(stops) + 1
    m = [[0.0] * n for _ in range(n)]
    for j, acc in enumerate(accs, start=1):
        m[0][j] = m[j][0] = _home_to_segment(graph, home, acc)
    for i, ai in enumerate(accs, start=1):
        for j, aj in enumerate(accs, start=1):
            if i != j:
                m[i][j] = _pair_dist(graph, ai, aj)
    return m, None


def _batched_road_lengths(graph, home: tuple[float, float], stops: list[dict]):
    """One Dijkstra per attachment node; returns matrix + length tables for crossings."""
    accs = [_segment_access(graph, s) for s in stops]
    n = len(stops) + 1
    m = [[0.0] * n for _ in range(n)]

    def _nodes_for_acc(acc: dict) -> list:
        return _access_nodes(graph, acc)

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
        ya, xa = float(graph.nodes[a]["y"]), float(graph.nodes[a]["x"])
        yb, xb = float(graph.nodes[b]["y"]), float(graph.nodes[b]["x"])
        return _haversine_km((ya, xa), (yb, xb)) * 1000.0

    def _seg_dist(nodes_a: list, nodes_b: list) -> float:
        return min(_node_dist(u, v) for u in nodes_a for v in nodes_b)

    for j, nj in enumerate(stop_nodes, start=1):
        m[0][j] = m[j][0] = _seg_dist([home_n], nj)
    for i, ni in enumerate(stop_nodes, start=1):
        for j, nj in enumerate(stop_nodes, start=1):
            if i != j:
                m[i][j] = _seg_dist(ni, nj)
    return m, lengths


def _road_matrix(graph, home: tuple[float, float], stops: list[dict]) -> tuple[list[list[float]], dict | None]:
    """Distance matrix: index 0 = home, 1..n = segment line (min road dist along access points)."""
    if graph is None:
        return _haversine_matrix(home, stops, None)
    return _batched_road_lengths(graph, home, stops)


def _stops_only_matrix(
    graph, stops: list[dict],
) -> tuple[list[list[float]], dict | None]:
    """n×n road meters between stops only (0-indexed); home not included."""
    accs = [_segment_access(graph, s) for s in stops]
    n = len(stops)
    if n == 0:
        return [[]], None
    if graph is None:
        m = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i != j:
                    m[i][j] = _pair_dist(None, accs[i], accs[j])
        return m, None

    def _nodes_for_acc(acc: dict) -> list:
        return _access_nodes(graph, acc)

    stop_nodes = [_nodes_for_acc(a) for a in accs]
    all_nodes = {nd for pair in stop_nodes for nd in pair}
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
        ya, xa = float(graph.nodes[a]["y"]), float(graph.nodes[a]["x"])
        yb, xb = float(graph.nodes[b]["y"]), float(graph.nodes[b]["x"])
        return _haversine_km((ya, xa), (yb, xb)) * 1000.0

    def _seg_dist(nodes_a: list, nodes_b: list) -> float:
        return min(_node_dist(u, v) for u in nodes_a for v in nodes_b)

    m = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                m[i][j] = _seg_dist(stop_nodes[i], stop_nodes[j])
    return m, lengths


def _two_opt_max_passes(n_stops: int) -> int:
    if n_stops <= 35:
        return 30
    if n_stops <= 60:
        return 20
    return 12


def _nearest_neighbor(matrix, start_idx, stop_indices):
    route, unvisited, cur = [], list(stop_indices), start_idx
    while unvisited:
        nxt = min(unvisited, key=lambda j: matrix[cur][j])
        route.append(nxt)
        unvisited.remove(nxt)
        cur = nxt
    return route


def _far_first_neighbor(matrix, start_idx, stop_indices):
    """Field workflow: hit the farthest zone/stop from home first, then chain inward."""
    if not stop_indices:
        return []
    first = max(stop_indices, key=lambda j: matrix[start_idx][j])
    return [first] + _nearest_neighbor(matrix, first, [j for j in stop_indices if j != first])


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


def _or_opt(matrix, start_idx, route, *, max_rounds: int = 4) -> list:
    """Relocate one stop at a time — helps when 2-opt plateaus."""
    if len(route) < 4:
        return route
    best = list(route)
    best_d = _path_len(matrix, start_idx, best)
    for _ in range(max_rounds):
        improved = False
        for i in range(len(best)):
            city = best.pop(i)
            for pos in range(len(best) + 1):
                trial = best[:pos] + [city] + best[pos:]
                d = _path_len(matrix, start_idx, trial)
                if d + 1e-6 < best_d:
                    best, best_d, improved = trial, d, True
                    break
            else:
                best.insert(i, city)
            if improved:
                break
        if not improved:
            break
    return best


def _ortools_matrix_route(matrix, n_stops: int) -> list[int] | None:
    """Optional OR-Tools TSP on the road matrix (10–15 stops when package installed)."""
    if n_stops <= EXACT_MATRIX_MAX_STOPS or n_stops > ORTOOLS_MATRIX_MAX_STOPS:
        return None
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except ImportError:
        return None
    try:
        manager = pywrapcp.RoutingIndexManager(n_stops + 1, 1, 0)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            a = manager.IndexToNode(from_index)
            b = manager.IndexToNode(to_index)
            return int(matrix[a][b])

        cb_idx = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(cb_idx)
        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        params.time_limit.seconds = 8
        solution = routing.SolveWithParameters(params)
        if not solution:
            return None
        index = routing.Start(0)
        route: list[int] = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != 0:
                route.append(node)
            index = solution.Value(routing.NextVar(index))
        return route if len(route) == n_stops else None
    except Exception:
        return None


def retrace_only(
    ordered_stops: list[dict],
    home: tuple[float, float],
    data_dir: str,
    *,
    abort=None,
) -> dict:
    """Rebuild polylines/miles for a manual stop order (no re-optimize)."""
    route = build_route(ordered_stops, home, data_dir, abort=abort)
    return {"order": ordered_stops, "route": route, "graph": route.get("graph", False)}


def _exact_matrix_route(matrix, n_stops: int) -> list[int] | None:
    """Brute-force optimal visit order on the road matrix (small n only)."""
    if n_stops > EXACT_MATRIX_MAX_STOPS:
        return None
    best_route: list[int] | None = None
    best_d = float("inf")
    for perm in itertools.permutations(range(1, n_stops + 1)):
        r = list(perm)
        d = _path_len(matrix, 0, r)
        if d < best_d:
            best_d, best_route = d, r
    return best_route


def _cached_refine_passes(n_stops: int) -> int:
    if n_stops <= 20:
        return 6
    if n_stops <= 40:
        return 4
    return 0


def _polish_rounds(n_stops: int) -> int:
    if n_stops <= 15:
        return 2
    if n_stops <= 40:
        return 1
    return 0


def _grid_clusters(stops: list[dict]) -> list[list[dict]]:
    """Group stops into geographic cells (~4 stops per cell on average)."""
    n = len(stops)
    if n < 2:
        return [list(stops)]
    lats = [float(s["lat"]) for s in stops]
    lons = [float(s["lon"]) for s in stops]
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    pad = max(0.0002, (lat_max - lat_min + lon_max - lon_min) * 0.02)
    lat_min -= pad
    lat_max += pad
    lon_min -= pad
    lon_max += pad
    dlat = lat_max - lat_min or 1e-9
    dlon = lon_max - lon_min or 1e-9
    # Coarser cells → fewer, larger zones (finish an area before leaving).
    n_side = max(2, min(8, int(round(math.sqrt(n / 5.5)))))
    buckets: dict[tuple[int, int], list[dict]] = {}
    for s in stops:
        lat, lon = float(s["lat"]), float(s["lon"])
        iy = min(n_side - 1, int((lat - lat_min) / dlat * n_side))
        ix = min(n_side - 1, int((lon - lon_min) / dlon * n_side))
        buckets.setdefault((iy, ix), []).append(s)
    clusters = list(buckets.values())
    return clusters if len(clusters) > 1 else [list(stops)]


def _pseudo_stop(lat: float, lon: float) -> dict:
    return {
        "begin_lat": lat, "begin_lon": lon, "end_lat": lat, "end_lon": lon,
        "lat": lat, "lon": lon, "id": "0",
    }


def _cluster_centroid(home: tuple[float, float], cluster: list[dict], graph) -> float:
    """Road meters from home to cluster centroid (for far-to-near zone order)."""
    la = sum(float(s["lat"]) for s in cluster) / len(cluster)
    lo = sum(float(s["lon"]) for s in cluster) / len(cluster)
    if graph is not None:
        return road_router.road_distance_m(graph, home, (la, lo))
    return _haversine_km(home, (la, lo)) * 1000.0


def _order_clusters_far_to_near(
    home: tuple[float, float], clusters: list[list[dict]], graph,
) -> list[list[dict]]:
    """Farthest zone from home first, then work back toward home — finish each zone before the next."""
    if len(clusters) <= 1:
        return clusters
    return sorted(clusters, key=lambda cl: _cluster_centroid(home, cl, graph), reverse=True)


def _tour_from_start(
    graph,
    start: tuple[float, float],
    stops: list[dict],
    *,
    allow_refine: bool = True,
) -> list[dict]:
    """TSP on a subset, entering from start (previous zone exit or home)."""
    n = len(stops)
    if n == 0:
        return []
    if n == 1:
        return list(stops)

    matrix, lengths = _road_matrix(graph, start, stops)
    exact = _exact_matrix_route(matrix, n)
    if exact is not None:
        route = exact
    else:
        route = _nearest_neighbor(matrix, 0, list(range(1, n + 1)))
        route = _two_opt(matrix, 0, route, max_passes=_two_opt_max_passes(n))
        if n <= 30:
            route = _or_opt(matrix, 0, route, max_rounds=2)

    ordered = [stops[i - 1] for i in route]
    if graph is not None and lengths is not None and allow_refine and 3 <= n <= 22:
        ordered = _refine_tour_2opt_cached(
            graph, start, ordered, lengths, max_passes=4)
    elif graph is not None and lengths is not None:
        ordered = _assign_crossings(graph, start, ordered, lengths=lengths)
    return ordered


def _path_len_open(matrix, route: list[int]) -> float:
    if len(route) < 2:
        return 0.0
    return sum(matrix[route[i]][route[i + 1]] for i in range(len(route) - 1))


def _two_opt_open(matrix, route: list[int], max_passes: int = 8) -> list[int]:
    """2-opt along a stop-to-stop path only (open path — no depot)."""
    if len(route) < 4:
        return route
    best, best_d, improved, passes = list(route), _path_len_open(matrix, route), True, 0
    while improved and passes < max_passes:
        improved, passes = False, passes + 1
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                if j - i == 1:
                    continue
                cand = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                cand_d = _path_len_open(matrix, cand)
                if cand_d + 1e-6 < best_d:
                    best, best_d, improved = cand, cand_d, True
    return best


def _or_opt_open(matrix, route: list[int], *, max_rounds: int = 3) -> list[int]:
    """Relocate one stop on an open path — helps when 2-opt plateaus."""
    if len(route) < 4:
        return route
    best = list(route)
    best_d = _path_len_open(matrix, best)
    for _ in range(max_rounds):
        improved = False
        for i in range(len(best)):
            city = best.pop(i)
            for pos in range(len(best) + 1):
                trial = best[:pos] + [city] + best[pos:]
                d = _path_len_open(matrix, trial)
                if d + 1e-6 < best_d:
                    best, best_d, improved = trial, d, True
                    break
            else:
                best.insert(i, city)
            if improved:
                break
        if not improved:
            break
    return best


def _exact_open_path(matrix, n_stops: int) -> list[int] | None:
    """Brute-force best open path on the stop-only matrix (small n only)."""
    if n_stops > EXACT_MATRIX_MAX_STOPS:
        return None
    best_route: list[int] | None = None
    best_d = float("inf")
    for perm in itertools.permutations(range(n_stops)):
        r = list(perm)
        if n_stops < 2:
            d = 0.0
        else:
            d = _path_len_open(matrix, r)
        if d < best_d:
            best_d, best_route = d, r
    return best_route


def _open_path_heuristic(matrix, n_stops: int) -> list[int]:
    """Try each start; NN chain + open 2-opt/or-opt; pick lowest path cost."""
    if n_stops <= 1:
        return list(range(n_stops))
    best_route: list[int] | None = None
    best_d = float("inf")
    for start in range(n_stops):
        route = [start]
        rem = set(range(n_stops)) - {start}
        cur = start
        while rem:
            nxt = min(rem, key=lambda j: matrix[cur][j])
            route.append(nxt)
            rem.remove(nxt)
            cur = nxt
        if n_stops >= 5:
            route = _two_opt_open(matrix, route, max_passes=_two_opt_max_passes(n_stops))
        if n_stops <= 50:
            route = _or_opt_open(matrix, route, max_rounds=2 if n_stops <= 30 else 1)
        d = _path_len_open(matrix, route)
        if d < best_d:
            best_d, best_route = d, route
    return best_route or [0]


def _assign_crossings_open(
    graph,
    ordered: list[dict],
    lengths: dict | None = None,
) -> list[dict]:
    """Chain crossings stop-to-stop; site 1 oriented toward site 2 (no home leg)."""
    if not ordered:
        return ordered
    if len(ordered) == 1:
        stop = ordered[0]
        locked = stop.get("cross_side") if stop.get("pick_cross_locked") else None
        if locked in ("begin", "end"):
            lat, lon, side = _locked_cross(stop, locked)
        else:
            lat, lon, side = _cross_begin_or_end(
                graph, lengths, (float(stop["lat"]), float(stop["lon"])), stop)
        stop["cross_lat"], stop["cross_lon"], stop["cross_side"] = lat, lon, side
        return ordered

    s0 = ordered[0]
    locked0 = s0.get("cross_side") if s0.get("pick_cross_locked") else None
    if locked0 in ("begin", "end"):
        lat, lon, side = _locked_cross(s0, locked0)
    else:
        toward = (float(ordered[1]["lat"]), float(ordered[1]["lon"]))
        lat, lon, side = _cross_begin_or_end(graph, lengths, toward, s0)
    s0["cross_lat"], s0["cross_lon"], s0["cross_side"] = lat, lon, side

    cur = (lat, lon)
    for stop in ordered[1:]:
        locked = stop.get("cross_side") if stop.get("pick_cross_locked") else None
        if locked in ("begin", "end"):
            lat, lon, side = _locked_cross(stop, locked)
        else:
            lat, lon, side = _cross_begin_or_end(graph, lengths, cur, stop)
        stop["cross_lat"], stop["cross_lon"], stop["cross_side"] = lat, lon, side
        cur = (lat, lon)
    return _slide_crossings(graph, ordered, lengths)


def _endpoint_distances(
    graph,
    lengths: dict | None,
    cur: tuple[float, float],
    stop: dict,
) -> tuple[float, float]:
    seg_b, seg_e = _seg_endpoints(stop)
    return (
        _cached_dist(graph, lengths, cur, seg_b),
        _cached_dist(graph, lengths, cur, seg_e),
    )


def _set_crossing_side(stop: dict, side: str) -> tuple[float, float]:
    lat, lon, side = _locked_cross(stop, side)
    stop["cross_lat"], stop["cross_lon"], stop["cross_side"] = lat, lon, side
    return lat, lon


def _nearest_endpoint_from(
    graph,
    lengths: dict | None,
    cur: tuple[float, float],
    stop: dict,
) -> tuple[float, str]:
    d_b, d_e = _endpoint_distances(graph, lengths, cur, stop)
    if d_b <= d_e:
        return d_b, "begin"
    return d_e, "end"


def _resolve_anchor(
    home: tuple[float, float],
    start: tuple[float, float] | None = None,
) -> tuple[float, float]:
    """Day-start point: live GPS when provided, else setup origin."""
    if start is not None:
        try:
            la, lo = float(start[0]), float(start[1])
        except (TypeError, ValueError):
            la, lo = 0.0, 0.0
        if abs(la) > 1e-6 or abs(lo) > 1e-6:
            return la, lo
    return float(home[0]), float(home[1])


def _slide_crossings(
    graph,
    ordered: list[dict],
    lengths: dict | None,
    *,
    home: tuple[float, float] | None = None,
) -> list[dict]:
    """Shift each crossing along its line to cut incoming + outgoing miles."""
    n = len(ordered)
    if n < 1:
        return ordered
    if n < 2 and home is None:
        return ordered
    for _round in range(2):
        for i, stop in enumerate(ordered):
            if stop.get("pick_cross_locked") and stop.get("cross_side") in ("begin", "end"):
                continue
            if stop.get("field_lat") is not None and stop.get("field_lon") is not None:
                continue
            prev = None
            if i == 0:
                if home is not None:
                    prev = (float(home[0]), float(home[1]))
            elif ordered[i - 1].get("cross_lat") is not None:
                prev = (float(ordered[i - 1]["cross_lat"]), float(ordered[i - 1]["cross_lon"]))
            nxt = None
            if i + 1 < n and ordered[i + 1].get("cross_lat") is not None:
                nxt = (float(ordered[i + 1]["cross_lat"]), float(ordered[i + 1]["cross_lon"]))
            best = None
            best_d = float("inf")
            for lat, lon, side in _seg_candidates(stop):
                d = 0.0
                if prev is not None:
                    d += _cached_dist(graph, lengths, prev, (lat, lon))
                if nxt is not None:
                    d += _cached_dist(graph, lengths, (lat, lon), nxt)
                if d < best_d:
                    best_d = d
                    best = (lat, lon, side)
            if best is not None:
                stop["cross_lat"], stop["cross_lon"], stop["cross_side"] = best
    return ordered


def _min_dist_to_stop(
    graph,
    lengths: dict | None,
    pt: tuple[float, float],
    stop: dict,
) -> float:
    return min(
        _cached_dist(graph, lengths, pt, (lat, lon))
        for lat, lon, _side in _seg_candidates(stop)
    )


def _nearest_stop_index(
    graph,
    lengths: dict | None,
    pt: tuple[float, float],
    stops: list[dict],
) -> int:
    return min(
        range(len(stops)),
        key=lambda i: _min_dist_to_stop(graph, lengths, pt, stops[i]),
    )


def _exact_open_path_from_start(
    matrix: list[list[float]],
    n_stops: int,
    start_idx: int,
) -> list[int] | None:
    """Best open path on stop-only matrix with a fixed first stop."""
    if n_stops > EXACT_MATRIX_MAX_STOPS or n_stops < 2:
        return None
    rest = [i for i in range(n_stops) if i != start_idx]
    best_route: list[int] | None = None
    best_d = float("inf")
    for perm in itertools.permutations(rest):
        r = [start_idx] + list(perm)
        d = _path_len_open(matrix, r)
        if d < best_d:
            best_d, best_route = d, r
    return best_route


def _open_path_heuristic_from_start(
    matrix: list[list[float]],
    n_stops: int,
    start_idx: int,
) -> list[int]:
    route = [start_idx]
    rem = set(range(n_stops)) - {start_idx}
    cur = start_idx
    while rem:
        nxt = min(rem, key=lambda j: matrix[cur][j])
        route.append(nxt)
        rem.remove(nxt)
        cur = nxt
    if n_stops >= 4:
        route = _two_opt_open(matrix, route, max_passes=_two_opt_max_passes(n_stops))
    if n_stops <= 50:
        route = _or_opt_open(matrix, route, max_rounds=2 if n_stops <= 30 else 1)
    return route


def _optimize_cluster_from_entry(
    entry: tuple[float, float],
    cluster: list[dict],
    graph,
) -> list[dict]:
    """Open-path tour inside one zone, entering at the stop nearest to entry."""
    n = len(cluster)
    if n <= 1:
        return copy.deepcopy(cluster)
    work = copy.deepcopy(cluster)
    matrix, lengths = _stops_only_matrix(graph, work)
    start_idx = _nearest_stop_index(graph, lengths, entry, work)
    route_idx = _exact_open_path_from_start(matrix, n, start_idx)
    if route_idx is None:
        route_idx = _open_path_heuristic_from_start(matrix, n, start_idx)
    return [work[i] for i in route_idx]


def _cluster_entry_dist(
    anchor: tuple[float, float],
    cluster: list[dict],
    graph,
) -> float:
    """Road/hav meters from day-start to cluster centroid."""
    la = sum(float(s["lat"]) for s in cluster) / len(cluster)
    lo = sum(float(s["lon"]) for s in cluster) / len(cluster)
    if graph is not None:
        return road_router.road_distance_m(graph, anchor, (la, lo))
    return _haversine_km(anchor, (la, lo)) * 1000.0


def _order_clusters_near_to_far(
    anchor: tuple[float, float],
    clusters: list[list[dict]],
    graph,
) -> list[list[dict]]:
    """Visit nearby zones first, then push outward — finish each area before leaving."""
    if len(clusters) <= 1:
        return clusters
    return sorted(clusters, key=lambda cl: _cluster_entry_dist(anchor, cl, graph))


def _stop_midpoint(stop: dict) -> tuple[float, float]:
    return float(stop["lat"]), float(stop["lon"])


def _order_stops_field(
    stops: list[dict],
    anchor: tuple[float, float],
    graph,
) -> list[dict]:
    """Zone sweep + open-path legs: anchor -> zone1 -> zone2 -> ..."""
    n = len(stops)
    if n <= 1:
        return copy.deepcopy(stops)
    work = copy.deepcopy(stops)
    use_zones = n >= ZONE_MIN_STOPS
    if not use_zones:
        return _optimize_cluster_from_entry(anchor, work, graph)

    clusters = _grid_clusters(work)
    clusters = _order_clusters_near_to_far(anchor, clusters, graph)
    ordered: list[dict] = []
    entry = anchor
    for zi, cluster in enumerate(clusters, start=1):
        chunk = _optimize_cluster_from_entry(entry, cluster, graph)
        for s in chunk:
            s["route_zone"] = zi
        ordered.extend(chunk)
        if chunk:
            entry = _stop_midpoint(chunk[-1])
    return ordered


def _open_path_cost_assigned(
    graph,
    ordered: list[dict],
    lengths: dict | None,
) -> float:
    """Drive meters along assigned crossings (open path, no depot)."""
    if len(ordered) < 2:
        return 0.0
    trial = _assign_crossings_open(graph, copy.deepcopy(ordered), lengths=lengths)
    cur = _stop_pt(trial[0])
    total = 0.0
    for s in trial[1:]:
        nxt = _stop_pt(s)
        total += _cached_dist(graph, lengths, cur, nxt)
        cur = nxt
    return total


def _refine_open_order(
    graph,
    ordered: list[dict],
    lengths: dict | None,
    *,
    max_passes: int = 6,
) -> list[dict]:
    """2-opt on visit order using true open-path crossing cost."""
    if graph is None or lengths is None or len(ordered) < 4:
        return _assign_crossings_open(graph, ordered, lengths=lengths)
    best = copy.deepcopy(ordered)
    best_d = _open_path_cost_assigned(graph, best, lengths)
    improved, passes = True, 0
    while improved and passes < max_passes:
        improved, passes = False, passes + 1
        n = len(best)
        for i in range(n - 1):
            for j in range(i + 1, n):
                if j - i == 1:
                    continue
                cand = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                d = _open_path_cost_assigned(graph, cand, lengths)
                if d + 1e-4 < best_d:
                    best, best_d, improved = cand, d, True
    return _assign_crossings_open(graph, best, lengths=lengths)


def _optimize_open_path(stops: list[dict], graph, *, anchor: tuple[float, float] | None = None) -> list[dict]:
    """Order stops to minimize road miles site 1 -> site N (open Hamiltonian path)."""
    n = len(stops)
    if n <= 1:
        return list(stops)
    if anchor is not None:
        return _optimize_cluster_from_entry(anchor, stops, graph)
    matrix, lengths = _stops_only_matrix(graph, stops)
    route_idx = _exact_open_path(matrix, n)
    if route_idx is None:
        route_idx = _open_path_heuristic(matrix, n)
    ordered = [stops[i] for i in route_idx]
    return _assign_crossings_open(graph, ordered, lengths=lengths)


def _tour_cluster_trail_back(
    home: tuple[float, float],
    cluster: list[dict],
    graph,
) -> list[dict]:
    """Inside one zone: farthest from home first, chain stop-to-stop back (never 2-opt from home)."""
    n = len(cluster)
    if n <= 1:
        return list(cluster)
    matrix, _ = _road_matrix(graph, home, cluster)
    first = max(range(1, n + 1), key=lambda j: matrix[0][j])
    route, rem, cur = [first], set(range(1, n + 1)) - {first}, first
    while rem:
        nxt = min(rem, key=lambda j: matrix[cur][j])
        route.append(nxt)
        rem.remove(nxt)
        cur = nxt
    if n >= 5:
        route = _two_opt_open(matrix, route, max_passes=8)
    return [cluster[i - 1] for i in route]


def _optimize_zoned(
    stops: list[dict],
    home: tuple[float, float],
    graph,
    *,
    anchor: tuple[float, float] | None = None,
) -> list[dict]:
    """Zone sweep from anchor; kept for callers that already import this helper."""
    pt = anchor if anchor is not None else (float(home[0]), float(home[1]))
    return _order_stops_field(stops, pt, graph)


def _matrix_tour(
    graph,
    home: tuple[float, float],
    stops: list[dict],
    n: int,
) -> list[int]:
    """Return matrix indices 1..n visit order (flat TSP, may backtrack across map)."""
    matrix, _ = _road_matrix(graph, home, stops)
    exact = _exact_matrix_route(matrix, n)
    if exact is not None:
        return exact
    ort = _ortools_matrix_route(matrix, n)
    if ort is not None:
        return ort
    seed = _far_first_neighbor(matrix, 0, list(range(1, n + 1)))
    route = _two_opt(matrix, 0, seed, max_passes=_two_opt_max_passes(len(seed)))
    if len(route) <= 50:
        route = _or_opt(matrix, 0, route, max_rounds=3 if n <= 30 else 1)
    return route


def _finish_crossings(
    graph,
    home: tuple[float, float],
    ordered: list[dict],
    stops: list[dict],
    *,
    zoned: bool,
) -> list[dict]:
    """Assign crossings from real home; optional polish (skipped after zoned — keeps areas clean)."""
    lengths = None
    if graph is not None and _HAS_NX:
        _, lengths = _batched_road_lengths(graph, home, stops)
    ordered = _assign_crossings(graph, home, ordered, lengths=lengths)
    if zoned or graph is None or lengths is None:
        return ordered
    if len(ordered) <= 40:
        ordered = _refine_tour_2opt_cached(
            graph, home, ordered, lengths, max_passes=_cached_refine_passes(len(ordered)))
    pr = _polish_rounds(len(ordered))
    if pr:
        ordered = _polish_crossings(graph, home, ordered, lengths, max_rounds=pr)
    return ordered


def optimize(
    stops: list[dict],
    home: tuple[float, float],
    data_dir: str,
    *,
    start: tuple[float, float] | None = None,
) -> dict:
    """Suggest stop order: zone sweep from GPS/start, open-path miles between sites."""
    if not stops:
        return {"order": [], "graph": False}

    n = len(stops)
    if n > MAX_ORDER_STOPS:
        stops = stops[:MAX_ORDER_STOPS]
        n = len(stops)

    graph, uncovered = _covering_graph(data_dir, stops)
    anchor = _resolve_anchor(home, start)
    ordered = _order_stops_field(stops, anchor, graph)

    lengths = None
    if graph is not None:
        _, lengths = _stops_only_matrix(graph, ordered)
    zoned = n >= ZONE_MIN_STOPS
    refine_passes = 0
    if graph is not None and not zoned:
        refine_passes = _cached_refine_passes(len(ordered))
    if refine_passes and lengths is not None:
        ordered = _refine_open_order(
            graph, ordered, lengths, max_passes=refine_passes)
    else:
        ordered = _assign_crossings_open(graph, ordered, lengths=lengths)

    return {
        "order": ordered,
        "graph": graph is not None,
        "graph_uncovered": uncovered,
        "anchor": [anchor[0], anchor[1]],
        "zoned": zoned,
        "used_gps": start is not None,
    }


def assign_crossings_for_display(
    stops: list[dict],
    home: tuple[float, float],
    data_dir: str,
    *,
    start: tuple[float, float] | None = None,
) -> list[dict]:
    """Preview crossings for the same suggested order BUILD ROUTE will use."""
    if not stops:
        return stops
    graph, _uncovered = _covering_graph(data_dir, stops)
    anchor = _resolve_anchor(home, start)
    ordered = _order_stops_field(copy.deepcopy(stops), anchor, graph)
    _, lengths = _stops_only_matrix(graph, ordered) if graph else (None, None)
    return _assign_crossings_open(graph, ordered, lengths=lengths)


def sanitize_leg_polyline(
    poly: list,
    home: tuple[float, float],
    dest: tuple[float, float],
    *,
    max_leg_km: float = 100.0,
    max_jump_km: float = 8.0,
) -> list | None:
    """Drop outlier/jump points so map guide lines stay near the job area."""
    if not poly or len(poly) < 2:
        return None
    h = (float(home[0]), float(home[1]))
    d = (float(dest[0]), float(dest[1]))

    def near_job(lat: float, lon: float) -> bool:
        return (
            min(_haversine_km(h, (lat, lon)), _haversine_km(d, (lat, lon))) <= max_leg_km
        )

    cleaned: list[list[float]] = []
    for p in poly:
        lat, lon = float(p[0]), float(p[1])
        if near_job(lat, lon):
            cleaned.append([lat, lon])
    if len(cleaned) < 2:
        if near_job(h[0], h[1]) and near_job(d[0], d[1]):
            return [[h[0], h[1]], [d[0], d[1]]]
        return None

    chunks: list[list[list[float]]] = []
    cur = [cleaned[0]]
    for i in range(1, len(cleaned)):
        a = (cur[-1][0], cur[-1][1])
        b = (cleaned[i][0], cleaned[i][1])
        if _haversine_km(a, b) > max_jump_km:
            if len(cur) >= 2:
                chunks.append(cur)
            cur = [cleaned[i]]
        else:
            cur.append(cleaned[i])
    if len(cur) >= 2:
        chunks.append(cur)
    if not chunks:
        return [[h[0], h[1]], [d[0], d[1]]]

    def chunk_score(chunk: list[list[float]]) -> float:
        start = (chunk[0][0], chunk[0][1])
        return _haversine_km(h, start)

    best = min(chunks, key=chunk_score)
    if _haversine_km((best[0][0], best[0][1]), h) > 2.0:
        best = [[h[0], h[1]]] + best
    if _haversine_km((best[-1][0], best[-1][1]), d) > 0.05:
        best = best + [[d[0], d[1]]]
    if _haversine_km((best[0][0], best[0][1]), (best[-1][0], best[-1][1])) > max_leg_km * 1.5:
        return None
    return best


def build_site_legs(
    ordered_stops: list[dict],
    home: tuple[float, float],
    data_dir: str,
    *,
    graph=None,
) -> list[dict]:
    """Legs site 1 -> site 2 -> ... -> site N. Site 1 has 0 mi (you drive there).

    ``home`` is accepted so callers can pass origin; commute clocks attach in
    ``build_route`` / ``time_est.attach_to_route``.
    """
    _ = home
    if not ordered_stops:
        return []
    if graph is None:
        graph, _uncovered = _covering_graph(data_dir, ordered_stops)
    out: list[dict] = []
    prev = _stop_pt(ordered_stops[0])
    for i, stop in enumerate(ordered_stops):
        dest = _stop_pt(stop)
        entry: dict = {
            "index": i,
            "to_uid": stop["uid"],
            "to_id": stop.get("id"),
            "from": (
                "Site 1 (you drive here)"
                if i == 0
                else f"Site {ordered_stops[i - 1].get('id')}"
            ),
            "to": f"Site {stop.get('id')}",
            "polyline": [],
            "miles": 0.0,
            "drive_min": 0.0,
            "ok": False,
        }
        if i == 0:
            entry["polyline"] = [[dest[0], dest[1]]]
            entry["ok"] = True
            out.append(entry)
            continue
        if graph is not None and road_router.HAS_ROUTING:
            leg = road_router.route_between(graph, prev, dest, include_turns=False)
            coords = _snap_leg_end(leg.get("polyline") or [], dest)
            raw = [[float(c[0]), float(c[1])] for c in coords]
            clean = sanitize_leg_polyline(raw, prev, dest)
            entry["polyline"] = clean or [[prev[0], prev[1]], [dest[0], dest[1]]]
            entry["miles"] = float(leg.get("miles") or 0.0)
            entry["ok"] = bool(leg.get("ok")) and clean is not None
        else:
            entry["polyline"] = [[prev[0], prev[1]], [dest[0], dest[1]]]
            entry["miles"] = _haversine_km(prev, dest) * 0.621371
            entry["ok"] = True
        entry["drive_min"] = round(time_est.drive_min_from_miles(entry["miles"]), 1)
        out.append(entry)
        prev = dest
    return out


def build_route(
    ordered_stops: list[dict],
    home: tuple[float, float],
    data_dir: str,
    *,
    abort=None,
) -> dict:
    """Real road polyline tracing site 1 -> site 2 -> ... -> site N (no home legs).

    Home is used only for clock estimates (leave / get home), not the drive polyline.
    """
    if not ordered_stops:
        return {"polyline": [], "miles": 0.0, "legs": [], "graph": False}

    graph, graph_uncovered = _covering_graph(data_dir, ordered_stops)
    ordered = list(ordered_stops)
    lengths = None
    if graph is not None:
        _, lengths = _stops_only_matrix(graph, ordered)
    if any(s.get("cross_lat") is None or s.get("cross_lon") is None for s in ordered):
        ordered = _assign_crossings_open(graph, ordered, lengths=lengths)
    try:
        from core import street_intel
        street_intel.annotate_stops(ordered, data_dir)
    except Exception:
        pass

    if road_router.HAS_ROUTING and graph is not None:
        legs: list[dict] = []
        polyline, miles = [], 0.0
        failed = 0
        for i in range(len(ordered) - 1):
            if abort and abort():
                return {
                    "polyline": polyline,
                    "miles": miles,
                    "legs": legs,
                    "graph": True,
                    "graph_uncovered": False,
                    "aborted": True,
                }
            a = _stop_pt(ordered[i])
            b = _stop_pt(ordered[i + 1])
            leg = road_router.route_between(graph, a, b, include_turns=False)
            leg["from"] = f"Site {ordered[i]['id']}"
            leg["to"] = f"Site {ordered[i + 1]['id']}"
            coords = _snap_leg_end(leg.get("polyline") or [], b)
            leg["polyline"] = coords
            if not leg.get("ok"):
                failed += 1
            if coords:
                if polyline and _same_coord(polyline[-1], coords[0]):
                    polyline.extend(coords[1:])
                else:
                    polyline.extend(coords)
            if leg.get("ok"):
                miles += leg.get("miles", 0.0)
            legs.append(leg)
        out = {
            "polyline": polyline,
            "miles": miles,
            "legs": legs,
            "graph": True,
            "graph_uncovered": False,
            "site_legs": build_site_legs(ordered, home, data_dir, graph=graph),
        }
        if failed:
            out["failed_legs"] = failed
        time_est.attach_to_route(out, ordered, home, graph)
        return out

    pts = [_stop_pt(s) for s in ordered]
    polyline = [[p[0], p[1]] for p in pts]
    miles = (
        sum(_haversine_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) * 0.621371
        if len(pts) >= 2
        else 0.0
    )
    out = {
        "polyline": polyline,
        "miles": miles,
        "legs": [],
        "graph": False,
        "graph_uncovered": graph_uncovered,
        "site_legs": build_site_legs(ordered, home, data_dir, graph=None),
    }
    time_est.attach_to_route(out, ordered, home, None)
    return out


def build_routes_by_section(
    ordered_stops: list[dict],
    home: tuple[float, float],
    data_dir: str,
    *,
    abort=None,
) -> dict[str, dict]:
    """One route per day, in the order those sites appear in a merged visit list.

    A failed day is an empty route so the pre-merge line is not left on screen.
    If ``abort`` becomes true, the dict only has days finished before the stop;
    the caller must not save that partial set.
    """
    from core import route_sections

    out: dict[str, dict] = {}
    for label in route_sections.section_labels(ordered_stops):
        if abort and abort():
            return out
        group = route_sections.stops_for_section(ordered_stops, label)
        if not group:
            continue
        try:
            out[label] = build_route(group, home, data_dir, abort=abort)
        except Exception:  # noqa: BLE001 — a failed day must not keep the old line
            out[label] = route_sections.empty_route()
    return out
