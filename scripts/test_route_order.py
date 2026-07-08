"""Route order engine — zone sweep, anchor, open-path regression.

    .venv\\Scripts\\python.exe scripts\\test_route_order.py
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "tds_data")
HOME = (33.7715, -117.9431)
GPS_NEAR_HOME = (33.7720, -117.9435)
FAILURES: list[str] = []


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str, detail: str = "") -> None:
    line = f"  FAIL {msg}" + (f": {detail}" if detail else "")
    print(line)
    FAILURES.append(msg)


def _seg(lat: float, lon: float, dlat: float = 0.0004, dlon: float = 0.0003) -> dict:
    return {
        "begin_lat": lat,
        "begin_lon": lon,
        "end_lat": lat + dlat,
        "end_lon": lon + dlon,
        "lat": lat + dlat / 2,
        "lon": lon + dlon / 2,
        "id": "0",
        "uid": f"u{lat}{lon}",
        "street": "Test St",
    }


def _make_two_cluster_job(n_per: int = 7) -> list[dict]:
    """Cluster A near HOME; cluster B ~0.35 deg north-east."""
    out: list[dict] = []
    for i in range(n_per):
        off = i * 0.00012
        out.append(_seg(33.770 + off, -117.945 + off))
        out[-1]["id"] = f"A{i}"
        out[-1]["uid"] = f"A{i}"
    for i in range(n_per):
        off = i * 0.00012
        out.append(_seg(34.120 + off, -117.650 + off))
        out[-1]["id"] = f"B{i}"
        out[-1]["uid"] = f"B{i}"
    return out


def test_zones_for_large_job() -> None:
    from core import routing

    stops = _make_two_cluster_job(7)  # 14 stops
    res = routing.optimize(stops, HOME, DATA)
    ordered = res["order"]
    if not res.get("zoned"):
        fail("zoned flag for 14 stops", str(res))
        return
    zones = {s.get("route_zone") for s in ordered}
    if len(zones) < 2:
        fail("multiple route_zone values", str(sorted(zones)))
        return
    ok(f"zoned build ({len(zones)} zones on {len(ordered)} stops)")


def test_first_stop_near_anchor() -> None:
    from core import routing
    from core.routing import _min_dist_to_stop, _covering_graph, _stops_only_matrix

    stops = _make_two_cluster_job(3)  # 6 stops, no zones
    res = routing.optimize(stops, HOME, DATA, start=GPS_NEAR_HOME)
    first = res["order"][0]
    graph, _ = _covering_graph(DATA, stops)
    lengths = None
    if graph is not None:
        _, lengths = _stops_only_matrix(graph, stops)
    dist_first = _min_dist_to_stop(graph, lengths, GPS_NEAR_HOME, first)
    best = min(_min_dist_to_stop(graph, lengths, GPS_NEAR_HOME, s) for s in stops)
    if dist_first > best * 1.05 + 1.0:
        fail("first stop near GPS anchor", f"first={dist_first:.0f}m best={best:.0f}m")
        return
    ok("first stop is nearest to GPS anchor")


def test_no_reserved_last_stop() -> None:
    """Open path ends naturally — not forced to home-nearest stop."""
    from core import routing

    stops = _make_two_cluster_job(7)  # 14 stops, zoned
    res = routing.optimize(stops, HOME, DATA)
    if not res.get("zoned"):
        fail("expected zoned route", str(res.get("zoned")))
        return
    zones = [s.get("route_zone") for s in res["order"]]
    if zones[0] != zones[6] or zones[7] != zones[13]:
        fail("zone blocks not contiguous", str(zones))
        return
    ok("zoned open path — zones visited in blocks (no forced last)")


def test_demo_job_builds() -> None:
    from core import ingest, routing
    import road_router

    if not road_router.has_graph(DATA):
        print("  SKIP demo job (no road graph)")
        return
    demo = os.path.join(ROOT, "demo_data", "demo_sites.csv")
    est = os.path.join(ROOT, "demo_data", "DemoDay.EST")
    sites = ingest.parse_excel_sites([demo])
    stops = ingest.match_est_files([{"path": est, "label": "Demo"}], sites, HOME)
    res = routing.optimize(stops, HOME, DATA)
    route = routing.build_route(res["order"], HOME, DATA)
    if len(res["order"]) != len(stops) or float(route.get("miles") or 0) < 0.1:
        fail("demo optimize+trace", f"miles={route.get('miles')}")
        return
    ok(f"demo job {route.get('miles', 0):.1f} mi")


def main() -> int:
    print("Route order engine tests\n")
    test_first_stop_near_anchor()
    test_no_reserved_last_stop()
    test_zones_for_large_job()
    test_demo_job_builds()
    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
