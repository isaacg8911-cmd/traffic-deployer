"""Route build timing + quality guard (optimize + trace on saved road graph).

    .venv\\Scripts\\python.exe scripts\\benchmark_route.py

Exit 0 if within time budgets and route geometry is valid.
"""
from __future__ import annotations

import copy
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "tds_data")
HOME = (33.7715, -117.9431)
DEMO_CSV = os.path.join(ROOT, "demo_data", "demo_sites.csv")
DEMO_EST = os.path.join(ROOT, "demo_data", "DemoDay.EST")

# Wall-clock budgets (seconds) on a typical field laptop.
TIME_BUDGET = {
    "demo": 60,
    31: 120,
    100: 120,
}


def _load_demo_stops():
    from core import ingest

    sites = ingest.parse_excel_sites([DEMO_CSV])
    cfgs = [{"path": DEMO_EST, "label": "DemoDay"}]
    return ingest.match_est_files(cfgs, sites, HOME)


def _expand_stops(base: list, count: int) -> list:
    out: list = []
    for i in range(count):
        s = copy.deepcopy(base[i % len(base)])
        s["id"] = f"{s.get('id', i)}-{i}"
        off = (i // len(base)) * 0.00015
        for key in ("begin_lat", "end_lat", "lat", "cross_lat", "field_lat"):
            if s.get(key) is not None:
                s[key] = float(s[key]) + off
        for key in ("begin_lon", "end_lon", "lon", "cross_lon", "field_lon"):
            if s.get(key) is not None:
                s[key] = float(s[key]) + off * 0.7
        out.append(s)
    return out


def _run_case(label: str, stops: list, budget_s: float) -> tuple[bool, str]:
    from core import routing
    import road_router

    if not road_router.has_graph(DATA):
        return False, "no road graph in tds_data"

    t0 = time.perf_counter()
    opt = routing.optimize(stops, HOME, DATA)
    ordered = opt["order"]
    route = routing.build_route(ordered, HOME, DATA)
    elapsed = time.perf_counter() - t0

    miles = float(route.get("miles") or 0)
    poly = route.get("polyline") or []
    ok = (
        len(ordered) == len(stops)
        and miles > 0.1
        and len(poly) >= 4
        and route.get("graph")
        and elapsed <= budget_s
    )
    detail = f"{elapsed:.1f}s, {miles:.1f} mi, {len(poly)} pts (budget {budget_s:.0f}s)"
    return ok, detail


def main() -> int:
    print(f"Route benchmark — {ROOT}\n")
    import road_router

    if not road_router.has_graph(DATA):
        print("  SKIP no road_graph.graphml — download road map first")
        return 0

    g = road_router.load_graph(DATA)
    print(f"  Graph: {len(g.nodes):,} nodes\n")

    base = _load_demo_stops()
    fails = 0
    for label, count in (("demo", len(base)), ("n31", 31), ("n100", 100)):
        stops = base if label == "demo" else _expand_stops(base, count)
        budget = TIME_BUDGET["demo" if label == "demo" else count]
        ok, detail = _run_case(label, stops, budget)
        mark = "OK" if ok else "FAIL"
        print(f"  [{mark}] {label} ({len(stops)} stops): {detail}")
        if not ok:
            fails += 1

    print()
    if fails:
        print(f"Benchmark failed ({fails} case(s)).")
        return 1
    print("Benchmark pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
