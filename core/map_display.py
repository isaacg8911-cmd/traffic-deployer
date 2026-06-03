"""Map-facing geometry: street-traced site lines and manual route order."""
from __future__ import annotations

import copy

import road_router

from core.routing import _assign_crossings, _cached_dist, _seg_endpoints, build_route


def segment_path_on_roads(
    data_dir: str,
    begin: tuple[float, float],
    end: tuple[float, float],
) -> list[list[float]]:
    """Lat/lon polyline along drive network between site begin and end."""
    if not road_router.has_graph(data_dir):
        return [[float(begin[0]), float(begin[1])], [float(end[0]), float(end[1])]]
    g = road_router.load_graph(data_dir)
    if g is None:
        return [[float(begin[0]), float(begin[1])], [float(end[0]), float(end[1])]]
    leg = road_router.route_between(g, begin, end, include_turns=False)
    coords = leg.get("polyline") or []
    if len(coords) >= 2:
        return [[float(c[0]), float(c[1])] for c in coords]
    return [[float(begin[0]), float(begin[1])], [float(end[0]), float(end[1])]]


def enrich_segment_paths(stops: list[dict], data_dir: str) -> None:
    for s in stops:
        b = (float(s["begin_lat"]), float(s["begin_lon"]))
        e = (float(s["end_lat"]), float(s["end_lon"]))
        s["segment_path"] = segment_path_on_roads(data_dir, b, e)


def _cross_point(stop: dict) -> tuple[float, float]:
    if stop.get("cross_lat") is not None and stop.get("cross_lon") is not None:
        return float(stop["cross_lat"]), float(stop["cross_lon"])
    return float(stop["lat"]), float(stop["lon"])


def auto_finish_order(
    home: tuple[float, float],
    picked: list[dict],
    pool: list[dict],
    data_dir: str,
) -> list[dict]:
    """Append remaining sites: nearest road miles from last pick (begin/end crossings)."""
    if not pool:
        return list(picked)
    graph = road_router.load_graph(data_dir) if road_router.has_graph(data_dir) else None
    lengths = None
    if graph is not None:
        try:
            import networkx as nx  # noqa: F401
            from core.routing import _batched_road_lengths

            all_stops = picked + pool
            _, lengths = _batched_road_lengths(graph, home, all_stops)
        except Exception:
            lengths = None
    order = copy.deepcopy(picked)
    rem = [s for s in pool if s["uid"] not in {p["uid"] for p in order}]
    if not order and rem:
        def home_dist(s: dict) -> float:
            seg_b, seg_e = _seg_endpoints(s)
            return max(
                _cached_dist(graph, lengths, (float(home[0]), float(home[1])), seg_b),
                _cached_dist(graph, lengths, (float(home[0]), float(home[1])), seg_e),
            )

        first = max(rem, key=home_dist)
        rem.remove(first)
        order.append(first)
    cur = _cross_point(order[-1]) if order else (float(home[0]), float(home[1]))
    while rem:
        def leg_cost(s: dict) -> float:
            seg_b, seg_e = _seg_endpoints(s)
            d_b = _cached_dist(graph, lengths, cur, seg_b)
            d_e = _cached_dist(graph, lengths, cur, seg_e)
            return min(d_b, d_e)

        nxt = min(rem, key=leg_cost)
        rem.remove(nxt)
        order.append(nxt)
        cur = _cross_point(nxt)
    return _assign_crossings(graph, home, order, lengths=lengths)


def apply_manual_order(
    home: tuple[float, float],
    ordered: list[dict],
    data_dir: str,
) -> dict:
    """Assign begin/end crossings and compute miles (no map drive polyline needed)."""
    graph = road_router.load_graph(data_dir) if road_router.has_graph(data_dir) else None
    lengths = None
    if graph is not None:
        try:
            from core.routing import _batched_road_lengths

            _, lengths = _batched_road_lengths(graph, home, ordered)
        except Exception:
            lengths = None
    ordered = _assign_crossings(graph, home, copy.deepcopy(ordered), lengths=lengths)
    enrich_segment_paths(ordered, data_dir)
    route = build_route(ordered, home, data_dir)
    return {"order": ordered, "route": route, "graph": route.get("graph", False)}
