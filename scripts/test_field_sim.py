"""Full field desk simulation — bundled validation job default; director job via TD_JOB_* env."""
from __future__ import annotations

import math
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from field_job_fixtures import resolve_field_job

DATA = os.path.join(ROOT, "tds_data")
FAILURES: list[str] = []
WARNS: list[str] = []


def ok(name: str, detail: str = ""):
    print(f"  OK  {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = ""):
    msg = f"{name}" + (f": {detail}" if detail else "")
    print(f"  FAIL {msg}")
    FAILURES.append(msg)


def warn(msg: str):
    print(f"  WARN {msg}")
    WARNS.append(msg)


def section(title: str):
    print(f"\n[{title}]")


def main() -> int:
    job = resolve_field_job()
    print(f"FIELD SIMULATION — {job.label} ({job.source}, desk, no GPS/counter)\n")

    from core import export, ingest, routing, validate
    from core.map_display import apply_manual_order, auto_finish_order
    from core.field_ready import check_all
    from core.offline_gate import evaluate as offline_gate_eval
    from core.setup_checklist import evaluate as setup_checklist_eval
    from core.state import RouteState, ca_now
    import road_router

    section("1. Job files")
    for p, _ in [(job.xls, "xls")] + list(job.ests):
        ok(f"exists {os.path.basename(p)}") if os.path.isfile(p) else fail(f"missing {p}")

    sites = ingest.parse_excel_sites([job.xls])
    ok("parse excel", f"{len(sites)} sites") if len(sites) >= 1 else fail("parse excel", f"{len(sites)}")
    cfgs = [{"path": p, "label": label} for p, label in job.ests]
    stops = ingest.match_est_files(cfgs, sites, job.home)
    ok("est match", f"{len(stops)} stops") if len(stops) >= 1 else fail("est match")
    rep = validate.validate_build([job.xls], cfgs, sites, stops, home=job.home)
    ok("validate") if rep["ok"] else fail("validate", "; ".join(rep.get("errors", [])))
    for w in rep.get("warnings", []):
        warn(w)

    section("2. Home save + checklist")
    d = tempfile.mkdtemp()
    st = RouteState(d, profile="FIELD_SIM")
    if not st.set_start_point(job.home[0], job.home[1], job.home_label):
        fail("set_start_point disk write")
    else:
        ok("set_start_point persists")
    st2 = RouteState(d, profile="FIELD_SIM")
    ok("home reload") if st2.load() and st2.default_home == job.home else fail("home reload")
    ck = setup_checklist_eval(
        home=st2.home,
        default_home=st2.default_home,
        excel_paths=[job.xls],
        est_paths=[p for p, _ in job.ests],
        has_graph=road_router.has_graph(DATA),
        route_miles=0,
    )
    ok("checklist blocks before route") if not ck["ok"] else fail("checklist pre-route", str(ck["blockers"]))

    section("3. Pick route -> Apply")
    miles = 0.0
    if not road_router.has_graph(DATA):
        fail("road graph missing")
    else:
        half = max(1, len(stops) // 2)
        t0 = time.time()
        finished = auto_finish_order(job.home, stops[:half], stops[half:], DATA)
        ok("auto_finish_order", f"{len(finished)} stops in {time.time()-t0:.1f}s") if len(finished) == len(stops) else fail("auto_finish_order")
        t0 = time.time()
        res = apply_manual_order(job.home, finished, DATA)
        route = res["route"]
        miles = float(route.get("miles") or 0)
        ok("apply_manual_order", f"{miles:.1f} mi in {time.time()-t0:.1f}s") if miles > 0 else fail("apply_manual_order")
        poly = route.get("polyline") or []
        if len(poly) >= 2 and res["order"]:
            last = res["order"][-1]
            clat = last.get("cross_lat", last.get("lat"))
            clon = last.get("cross_lon", last.get("lon"))
            if clat is not None and clon is not None:
                d_tail = math.hypot(poly[-1][0] - float(clat), poly[-1][1] - float(clon))
                ok("route ends at last stop", f"delta {d_tail:.4f}") if d_tail < 0.03 else fail(
                    "route ends at last stop", f"{d_tail:.4f}")
        st2.stops = res["order"]
        st2.route = route
        st2.excel_paths = [job.xls]
        st2.est_paths = [p for p, _ in job.ests]
        st2.save()

    section("4. Ready for offline gate")
    fr = check_all(ROOT, probe_gps=False, probe_counter=False, stop_server_after=True)
    gate = offline_gate_eval(fr, has_stops=True, route_miles=miles, graph_loaded=road_router.has_graph(DATA))
    ok("offline gate open") if gate["ok"] else fail("offline gate", "; ".join(gate["blockers"]))
    ck2 = setup_checklist_eval(
        home=st2.home,
        default_home=st2.default_home,
        excel_paths=[job.xls],
        est_paths=[p for p, _ in job.ests],
        has_graph=road_router.has_graph(DATA),
        route_miles=miles,
    )
    ok("setup checklist green") if ck2["ok"] else fail("setup checklist", "; ".join(ck2["blockers"]))

    section("5. Install -> Pickup -> Audit export")
    td, _ = ca_now()
    st2.stops[0].update({
        "installed": True, "serial": "SIM-001", "street": "Field St",
        "field_lat": job.home[0] + 0.01, "field_lon": job.home[1] + 0.01, "direction": "n",
        "counter_serial": "SIM-001", "counter_unit_id": "SIMU1",
        "counter_cleared": True, "date": td,
    })
    st2.stops[1]["skipped"] = True
    st2.stops[1]["date"] = td
    st2.stops[0]["picked_up"] = True
    st2.stops[0]["counter_download"] = True
    st2.stops[0]["counter_download_path"] = os.path.join(d, "fake.bin")

    aud = export.audit(st2.stops)
    ok("audit pass") if aud["ok"] else fail("audit", "; ".join(aud.get("missing", [])))
    xlsx = export.to_excel_bytes(st2.stops)
    ok("excel export", f"{len(xlsx)} bytes") if xlsx and len(xlsx) > 500 else fail("excel export")

    section("6. Auto-optimize path (sanity)")
    try:
        opt = routing.optimize(stops, job.home, DATA)
        ok("optimize", f"{len(opt.get('order', []))} stops") if len(opt.get("order", [])) == len(stops) else fail("optimize")
    except Exception as exc:
        fail("optimize", str(exc))

    print(f"\n{'=' * 55}")
    print(f"FAIL: {len(FAILURES)}  WARN: {len(WARNS)}")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
        print("\nFIELD SIM FAIL")
        return 1
    print(f"\nFIELD SIM PASS — {job.label} ({job.source}); GPS/counter Isaac-only at plug-in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
