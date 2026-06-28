"""Regression: GraphML string node coords (networkx path) must not break routing.

Desk tests used osmnx.load_graphml -> float coords. Work laptop can hit nx.read_graphml
-> string coords — that is what caused the subtract TypeError on Apply + Auto-optimize.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import road_router
from core import routing
from core.map_display import apply_manual_order

DATA = os.path.join(ROOT, "tds_data")
DEMO = os.path.join(ROOT, "demo_data", "demo_sites.csv")
HOME = (33.7715, -117.9431)


def _demo_stops():
    from core import ingest

    sites = ingest.parse_excel_sites([DEMO])
    est = os.path.join(ROOT, "demo_data", "DemoDay.EST")
    return ingest.match_est_files([{"path": est, "label": "Demo"}], sites, HOME)


def _clear_graph_cache() -> None:
    road_router._GRAPH_CACHE.clear()
    road_router._NODE_ARRAYS.clear()


def _assert_nx_graph_is_strings() -> None:
    """Prove the failure mode exists on raw networkx load (work-laptop class bug)."""
    import networkx as nx

    gpath = road_router.graph_path(DATA)
    G = nx.read_graphml(gpath)
    n = next(iter(G.nodes))
    y = G.nodes[n]["y"]
    if not isinstance(y, str):
        print(f"WARN: expected nx string coords, got {type(y).__name__}")


def _run_routing(label: str, data_dir: str) -> int:
    stops = _demo_stops()
    if len(stops) < 2:
        print(f"FAIL {label}: demo stops")
        return 1
    try:
        opt = routing.optimize(stops, HOME, data_dir)
        route = routing.build_route(opt["order"], HOME, data_dir)
        res = apply_manual_order(HOME, opt["order"], data_dir)
    except Exception as exc:
        print(f"FAIL {label}: {exc}")
        return 1
    print(
        f"OK {label} — optimize {len(opt['order'])} stops "
        f"{route.get('miles', 0):.1f} mi, apply {res['route'].get('miles', 0):.1f} mi")
    return 0


def main() -> int:
    if not road_router.has_graph(DATA):
        print("SKIP: no road graph in tds_data")
        return 0

    _assert_nx_graph_is_strings()

    if _run_routing("osmnx/default load", DATA):
        return 1

    # Force networkx-only load — same coord types work laptop can see.
    _clear_graph_cache()
    orig = road_router.HAS_OSMNX
    road_router.HAS_OSMNX = False
    try:
        G = road_router.load_graph(DATA)
        if G is None:
            print("FAIL nx-only load_graph returned None")
            return 1
        n = next(iter(G.nodes))
        y = G.nodes[n]["y"]
        if not isinstance(y, (int, float)):
            print(f"FAIL nx-only load left string coords: {type(y).__name__}")
            return 1
        if _run_routing("nx-only load (string graphml repro)", DATA):
            return 1
    finally:
        road_router.HAS_OSMNX = orig
        _clear_graph_cache()

    print("PASS string-graph-coords regression (osmnx + nx-only paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
