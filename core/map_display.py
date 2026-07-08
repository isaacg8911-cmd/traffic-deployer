"""Map-facing geometry: street-traced site lines and manual route order."""
from __future__ import annotations

import copy

import road_router

from core.routing import (
    _assign_crossings_open,
    _covering_graph,
    _optimize_cluster_from_entry,
    _order_stops_field,
    _resolve_anchor,
    _seg_endpoints,
    _stops_only_matrix,
    build_route,
)


def segment_path_on_roads(
    data_dir: str,
    begin: tuple[float, float],
    end: tuple[float, float],
) -> list[list[float]]:
    """Lat/lon polyline along drive network between site begin and end."""
    straight = [[float(begin[0]), float(begin[1])], [float(end[0]), float(end[1])]]
    if not road_router.has_graph(data_dir):
        return straight
    g = road_router.load_graph(data_dir)
    if g is None:
        return straight
    if not (road_router.covers_point(g, begin[0], begin[1])
            and road_router.covers_point(g, end[0], end[1])):
        return straight
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


def _finish_pick_order(
    order: list[dict],
    graph,
    data_dir: str,
) -> list[dict]:
    lengths = None
    if graph is not None:
        try:
            _, lengths = _stops_only_matrix(graph, order)
        except Exception:
            lengths = None
    return _assign_crossings_open(graph, copy.deepcopy(order), lengths=lengths)


def auto_finish_order(
    home: tuple[float, float],
    picked: list[dict],
    pool: list[dict],
    data_dir: str,
) -> list[dict]:
    """Append remaining sites using the same zone/open-path engine as auto-build."""
    if not pool:
        return list(picked)
    graph, _uncovered = _covering_graph(data_dir, picked + pool)
    order = copy.deepcopy(picked)
    rem = [s for s in pool if s["uid"] not in {p["uid"] for p in order}]
    if not order:
        anchor = _resolve_anchor(home, None)
        return _finish_pick_order(
            _order_stops_field(rem, anchor, graph), graph, data_dir)
    cur = _cross_point(order[-1])
    if rem:
        tail = _optimize_cluster_from_entry(cur, rem, graph)
        order.extend(tail)
    return _finish_pick_order(order, graph, data_dir)


def apply_manual_order(
    home: tuple[float, float],
    ordered: list[dict],
    data_dir: str,
) -> dict:
    """Assign begin/end crossings and compute miles (site 1 -> site N)."""
    del home
    graph, _uncovered = _covering_graph(data_dir, ordered)
    lengths = None
    if graph is not None:
        try:
            _, lengths = _stops_only_matrix(graph, ordered)
        except Exception:
            lengths = None
    ordered = _assign_crossings_open(graph, copy.deepcopy(ordered), lengths=lengths)
    route = build_route(ordered, (0.0, 0.0), data_dir)
    return {"order": ordered, "route": route, "graph": route.get("graph", False)}
