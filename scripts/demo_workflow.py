"""Headless desk test: demo Excel + EST through full pipeline."""
from __future__ import annotations

import math
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "tds_data")
DEMO_CSV = os.path.join(ROOT, "demo_data", "demo_sites.csv")
DEMO_EST = os.path.join(ROOT, "demo_data", "DemoDay.EST")
HOME = (33.7715, -117.9431)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    if ok:
        print(f"  OK  {name}")
    else:
        msg = f"{name}" + (f": {detail}" if detail else "")
        print(f"  FAIL {msg}")
        FAILURES.append(msg)


def main() -> int:
    print(f"Demo workflow — {ROOT}\n")
    from core import export, ingest, validate
    from core import routing
    from core.state import RouteState, ca_now
    import road_router

    check("demo csv", os.path.isfile(DEMO_CSV))
    check("demo est", os.path.isfile(DEMO_EST))
    if FAILURES:
        return 1

    sites = ingest.parse_excel_sites([DEMO_CSV])
    check("parse sites", len(sites) >= 5, f"got {len(sites)}")

    cfgs = [{"path": DEMO_EST, "label": "DemoDay"}]
    stops = ingest.match_est_files(cfgs, sites, HOME)
    check("est match", len(stops) >= 5, f"matched {len(stops)}")

    rep = validate.validate_build([DEMO_CSV], cfgs, sites, stops)
    check("validate", rep["ok"], "; ".join(rep.get("errors", [])))

    td, _ = ca_now()
    d = tempfile.mkdtemp()
    st = RouteState(d, profile="DEMO_WF")
    st.stops = [ingest.merge_stop_progress(None, s) for s in stops]
    st.home = HOME
    for s in st.stops:
        s["date"] = td
    check("state save", st.save())
    st2 = RouteState(d, profile="DEMO_WF")
    check("state load", st2.load() and len(st2.stops) == len(stops))

    if road_router.has_graph(DATA):
        try:
            opt = routing.optimize(list(st.stops), HOME, DATA)
            ordered = opt["order"]
            check("optimize", len(ordered) == len(stops))
            route = routing.build_route(ordered, HOME, DATA)
            check("build route", bool(route.get("polyline")) and route.get("miles", 0) > 0)
            poly = route.get("polyline") or []
            if len(poly) >= 2 and ordered:
                last = ordered[-1]
                clat = last.get("cross_lat", last.get("lat"))
                clon = last.get("cross_lon", last.get("lon"))
                if clat is not None and clon is not None:
                    d_tail = math.hypot(
                        poly[-1][0] - float(clat), poly[-1][1] - float(clon))
                    check("route ends at last stop", d_tail < 0.03, f"tail delta {d_tail:.4f}")
        except Exception as exc:
            check("routing", False, str(exc))
    else:
        print("  WARN no road graph — skip routing (download roads in Setup)")

    s0 = st.stops[0]
    s0.update({
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
        print(f"DEMO WORKFLOW FAILED ({len(FAILURES)}):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("DEMO WORKFLOW PASS — desk pipeline proven.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
