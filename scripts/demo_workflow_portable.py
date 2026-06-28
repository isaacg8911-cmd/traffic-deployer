"""Headless desk test using frozen portable layout (dist/TrafficDeployer)."""
from __future__ import annotations

import importlib
import math
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist", "TrafficDeployer")
EXE = os.path.join(DIST, "TrafficDeployer.exe")
INTERNAL = os.path.join(DIST, "_internal")
HOME = (33.7715, -117.9431)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  OK  {name}")
    else:
        msg = f"{name}" + (f": {detail}" if detail else "")
        print(f"  FAIL {msg}")
        FAILURES.append(msg)


def _purge_paths_modules() -> None:
    for mod in list(sys.modules):
        if mod == "ui.paths" or mod.startswith("ui.paths."):
            del sys.modules[mod]


def _frozen_env() -> None:
    sys.frozen = True  # type: ignore[attr-defined]
    sys.executable = EXE
    sys._MEIPASS = INTERNAL  # type: ignore[attr-defined]


def main() -> int:
    print(f"Portable demo workflow — {DIST}\n")

    if not os.path.isfile(EXE):
        check("portable exe", False, EXE)
        return 1

    _frozen_env()
    _purge_paths_modules()
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    import ui.paths as paths

    paths = importlib.reload(paths)
    ok, msg = paths.web_assets_ok()
    check("web assets", ok, msg)

    demo_csv = paths.DEMO_CSV
    demo_est = paths.DEMO_EST
    check("demo csv", os.path.isfile(demo_csv), demo_csv)
    check("demo est", os.path.isfile(demo_est), demo_est)
    if FAILURES:
        return 1

    from core import export, ingest, routing, validate
    from core.map_display import apply_manual_order
    from core.state import RouteState, ca_now
    import road_router

    data = paths.DATA_DIR
    route_data = data
    if not road_router.has_graph(data):
        build_graph = os.path.join(ROOT, "tds_data")
        if road_router.has_graph(build_graph):
            route_data = build_graph
            print(
                "  NOTE routing uses build PC tds_data "
                "(dist has no graph; work laptop has road_graph.graphml beside exe)")

    sites = ingest.parse_excel_sites([demo_csv])
    check("parse sites", len(sites) >= 5, f"got {len(sites)}")

    cfgs = [{"path": demo_est, "label": "DemoDay"}]
    stops = ingest.match_est_files(cfgs, sites, HOME)
    check("est match", len(stops) >= 5, f"matched {len(stops)}")

    rep = validate.validate_build([demo_csv], cfgs, sites, stops)
    check("validate", rep["ok"], "; ".join(rep.get("errors", [])))

    td, _ = ca_now()
    d = tempfile.mkdtemp()
    st = RouteState(d, profile="PORTABLE_DEMO")
    st.stops = [ingest.merge_stop_progress(None, s) for s in stops]
    st.home = HOME
    for s in st.stops:
        s["date"] = td
    check("state save", st.save())
    st2 = RouteState(d, profile="PORTABLE_DEMO")
    check("state load", st2.load() and len(st2.stops) == len(stops))

    if road_router.has_graph(route_data):
        try:
            opt = routing.optimize(list(st.stops), HOME, route_data)
            ordered = opt["order"]
            check("optimize", len(ordered) == len(stops))
            route = routing.build_route(ordered, HOME, route_data)
            check("build route", bool(route.get("polyline")) and route.get("miles", 0) > 0)
            res = apply_manual_order(HOME, ordered, route_data)
            check("apply route", float(res["route"].get("miles") or 0) > 0)
            poly = route.get("polyline") or []
            if len(poly) >= 2:
                d_home = math.hypot(poly[-1][0] - HOME[0], poly[-1][1] - HOME[1])
                check("route returns home", d_home < 0.02, f"tail delta {d_home:.4f}")
            road_router._GRAPH_CACHE.clear()
            road_router._NODE_ARRAYS.clear()
            orig_ox = road_router.HAS_OSMNX
            road_router.HAS_OSMNX = False
            try:
                opt2 = routing.optimize(list(st.stops), HOME, route_data)
                check("optimize nx-only graph", len(opt2.get("order", [])) == len(stops))
            finally:
                road_router.HAS_OSMNX = orig_ox
                road_router._GRAPH_CACHE.clear()
                road_router._NODE_ARRAYS.clear()
        except Exception as exc:
            check("routing", False, str(exc))
    else:
        print("  WARN no road graph — routing skipped")

    st.stops[0].update({
        "installed": True, "serial": "DEMO-001", "street": "Main St",
        "field_lat": 33.772, "field_lon": -117.943, "direction": "n",
    })
    st.stops[1]["skipped"] = True
    st.stops[1]["date"] = td

    aud = export.audit(st.stops)
    check("audit", aud["ok"], "; ".join(aud.get("missing", [])))
    xlsx = export.to_excel_bytes(st.stops)
    check("excel export", xlsx is not None and len(xlsx) > 500)

    print()
    if FAILURES:
        print(f"PORTABLE DEMO WORKFLOW FAILED ({len(FAILURES)}):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("PORTABLE DEMO WORKFLOW PASS — handoff layout proven.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
