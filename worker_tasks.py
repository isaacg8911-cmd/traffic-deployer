"""Out-of-process worker for heavy map/routing jobs.

Why a separate process: osmnx graph building and networkx Dijkstra are CPU-bound
pure-Python work that holds the GIL. Running them in a QThread would still freeze
the Qt UI ("not responding"). Running them as a child process keeps the window
fully responsive.

Usage (invoked by the app):
    python worker_tasks.py <input.json> <output.json>

input.json: {"task": "<name>", ...args}
output.json: {"ok": bool, ...result} or {"ok": false, "error": "..."}
"""
from __future__ import annotations

import json
import sys


def _download_roads(p: dict) -> dict:
    import road_router
    pts = [tuple(pt) for pt in p["points"]]
    info = road_router.download_area(pts, p["data_dir"])
    return {"ok": True, **info}


def _route(p: dict) -> dict:
    from core import routing
    home = tuple(p["home"])
    res = routing.optimize(p["stops"], home, p["data_dir"])
    ordered = res["order"]
    route = routing.build_route(ordered, home, p["data_dir"])
    return {"ok": True, "order": ordered, "route": route, "graph": res["graph"]}


def _navplan(p: dict) -> dict:
    import road_router
    from core import routing
    home = tuple(p["home"])
    start = tuple(p["start"])
    stops = p["stops"]  # already in visiting order, only the remaining ones
    if not (road_router.HAS_ROUTING and road_router.has_graph(p["data_dir"])):
        # No graph -> straight-line fallback plan handled by the app.
        return {"ok": True, "plan": [], "polyline": [], "miles": 0.0, "graph": False}
    graph = road_router.load_graph(p["data_dir"])
    pts = [start] + [routing._stop_pt(s) for s in stops]
    labels = ["start"] + [s["id"] for s in stops]
    plan = road_router.nav_plan(graph, pts, labels)
    return {"ok": True, **plan, "graph": True}


TASKS = {"download_roads": _download_roads, "route": _route, "navplan": _navplan}


def main():
    infile, outfile = sys.argv[1], sys.argv[2]
    try:
        with open(infile, "r", encoding="utf-8") as f:
            payload = json.load(f)
        fn = TASKS[payload["task"]]
        result = fn(payload)
    except Exception as exc:  # noqa: BLE001
        import traceback
        result = {"ok": False, "error": f"{exc}", "trace": traceback.format_exc()}
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(result, f, default=str)


if __name__ == "__main__":
    main()
