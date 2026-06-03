"""Route engine: order stops by the most efficient way to CROSS each street line.

Each site is a street segment (begin -> end). Routing ignores the midpoint;
it finds the best road approach to cross each segment line, orders segments to
minimize total drive miles, traces real streets home -> crossings -> home.

Full pipeline (ingest, road graph, matrix/2-opt, map trace, driving):
see ROUTING_AND_MAP.md in the project root.
"""
from __future__ import annotations

import copy
import itertools
import math

import road_router

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
# Zone-first ordering: finish a geographic area before driving to the next (reduces backtracking).
ZONE_MIN_STOPS = 8


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


def _cached_dist(graph, lengths: dict | None, a: tuple[float, float], b: tuple[float, float]) -> float:
    if graph is None:
        return _haversine_km(a, b) * 1000.0
    if lengths is not None:
        return road_router.distance_from_lengths(graph, lengths, a, b)
    return _road_m(graph, a, b)


def _access_pts(acc: dict) -> list[tuple[float, float]]:
    return [acc["begin"], acc["end"]]


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
    """Drive-to point is segment begin or end only (whichever is closer on the road)."""
    seg_b, seg_e = _seg_endpoints(stop)
    d_b = _cached_dist(graph, lengths, cur, seg_b)
    d_e = _cached_dist(graph, lengths, cur, seg_e)
    if d_b <= d_e:
        return seg_b[0], seg_b[1], "begin"
    return seg_e[0], seg_e[1], "end"


def _assign_crossings(
    graph,
    home: tuple[float, float],
    ordered: list[dict],
    lengths: dict | None = None,
) -> list[dict]:
    """Chain crossings using begin/end endpoints only."""
    cur = (float(home[0]), float(home[1]))
    for stop in ordered:
        lat, lon, side = _cross_begin_or_end(graph, lengths, cur, stop)
        stop["cross_lat"], stop["cross_lon"] = lat, lon
        stop["cross_side"] = side
        cur = (lat, lon)
    return ordered


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
    return m, lengths


def _road_matrix(graph, home: tuple[float, float], stops: list[dict]) -> tuple[list[list[float]], dict | None]:
    """Distance matrix: index 0 = home, 1..n = segment line (min road dist between access ends)."""
    if graph is None:
        return _haversine_matrix(home, stops, None)
    return _batched_road_lengths(graph, home, stops)


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


def retrace_only(ordered_stops: list[dict], home: tuple[float, float], data_dir: str) -> dict:
    """Rebuild polylines/miles for a manual stop order (no re-optimize)."""
    route = build_route(ordered_stops, home, data_dir)
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
    """2-opt along a stop-to-stop path only (no home depot — preserves far-first start)."""
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
) -> list[dict]:
    """Far zones first, trail back toward home; complete each zone before branching to the next."""
    clusters = _grid_clusters(stops)
    clusters = _order_clusters_far_to_near(home, clusters, graph)
    ordered: list[dict] = []
    for zi, cluster in enumerate(clusters, start=1):
        chunk = _tour_cluster_trail_back(home, cluster, graph)
        for s in chunk:
            s["route_zone"] = zi
        ordered.extend(chunk)
    return ordered


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


def optimize(stops: list[dict], home: tuple[float, float], data_dir: str) -> dict:
    """Order segments for minimum road miles to cross each street line."""
    if not stops:
        return {"order": [], "graph": False}

    n = len(stops)
    if n > MAX_ORDER_STOPS:
        stops = stops[:MAX_ORDER_STOPS]
        n = len(stops)

    graph = None
    if road_router.HAS_ROUTING and _HAS_NX and road_router.has_graph(data_dir):
        graph = road_router.load_graph(data_dir)

    use_zones = n >= ZONE_MIN_STOPS and graph is not None
    if use_zones:
        ordered = _optimize_zoned(stops, home, graph)
        ordered = _finish_crossings(graph, home, ordered, stops, zoned=True)
    else:
        route = _matrix_tour(graph, home, stops, n)
        ordered = [stops[i - 1] for i in route]
        ordered = _finish_crossings(graph, home, ordered, stops, zoned=False)
    return {"order": ordered, "graph": graph is not None}


def assign_crossings_for_display(
    stops: list[dict], home: tuple[float, float], data_dir: str
) -> list[dict]:
    """Set cross_lat/lon on stops for map preview (before full route build)."""
    if not stops:
        return stops
    graph = None
    lengths = None
    if road_router.HAS_ROUTING and road_router.has_graph(data_dir):
        graph = road_router.load_graph(data_dir)
        if graph is not None and _HAS_NX:
            _, lengths = _batched_road_lengths(graph, home, stops)
    out = copy.deepcopy(stops)
    return _assign_crossings(graph, home, out, lengths=lengths)


def build_route(ordered_stops: list[dict], home: tuple[float, float], data_dir: str) -> dict:
    """Real road polyline tracing home -> each line crossing -> home."""
    if not ordered_stops:
        return {"polyline": [], "miles": 0.0, "legs": [], "graph": False}

    graph = road_router.load_graph(data_dir) if road_router.has_graph(data_dir) else None
    ordered = list(ordered_stops)
    if graph is not None:
        _, lengths = _batched_road_lengths(graph, home, ordered)
    else:
        lengths = None
    if any(s.get("cross_lat") is None or s.get("cross_lon") is None for s in ordered):
        ordered = _assign_crossings(graph, home, ordered, lengths=lengths)
    try:
        from core import street_intel
        street_intel.annotate_stops(ordered, data_dir)
    except Exception:
        pass

    if road_router.HAS_ROUTING and graph is not None:
        targets = [(*_stop_pt(s), f"Site {s['id']}") for s in ordered]
        legs = road_router.directions_for_stops(
            graph, home, targets, include_turns=False)
        last = _stop_pt(ordered[-1])
        ret = road_router.route_between(graph, last, home, include_turns=False)
        ret["from"] = f"Stop {len(ordered)}"
        ret["to"] = "Home"
        legs.append(ret)
        polyline, miles = [], 0.0
        failed = 0
        for i, leg in enumerate(legs):
            coords = leg.get("polyline") or []
            if i < len(ordered):
                touch = _stop_pt(ordered[i])
                coords = _snap_leg_end(coords, touch)
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
        out = {"polyline": polyline, "miles": miles, "legs": legs, "graph": True}
        if failed:
            out["failed_legs"] = failed
        return out

    pts = [(float(home[0]), float(home[1]))] + [_stop_pt(s) for s in ordered] + [(float(home[0]), float(home[1]))]
    polyline = [[p[0], p[1]] for p in pts]
    miles = sum(_haversine_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) * 0.621371
    return {"polyline": polyline, "miles": miles, "legs": [], "graph": False}
