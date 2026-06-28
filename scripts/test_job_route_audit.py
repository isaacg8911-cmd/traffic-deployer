"""Headless job route audit: ingest + validate + pick-apply + auto-finish (bundled validation default)."""
from __future__ import annotations

import math
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from field_job_fixtures import resolve_field_job

DATA = os.path.join(ROOT, "tds_data")
FAILURES: list[str] = []
WARNS: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    if ok:
        msg = f"  OK  {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
    else:
        msg = f"{name}" + (f": {detail}" if detail else "")
        print(f"  FAIL {msg}")
        FAILURES.append(msg)


def warn(msg: str):
    print(f"  WARN {msg}")
    WARNS.append(msg)


def main() -> int:
    job = resolve_field_job()
    print(f"Job route audit — {job.label} ({job.source})\n")

    from core import ingest, routing, validate
    from core.map_display import apply_manual_order, auto_finish_order
    import road_router

    for p, _ in [(job.xls, "xls")] + list(job.ests):
        check(f"file exists {os.path.basename(p)}", os.path.isfile(p), p)

    sites = ingest.parse_excel_sites([job.xls])
    check("parse excel", len(sites) >= 1, f"{len(sites)} sites")

    cfgs = [{"path": p, "label": label} for p, label in job.ests]
    stops = ingest.match_est_files(cfgs, sites, job.home)
    check("est match", len(stops) >= 1, f"{len(stops)} stops")

    rep = validate.validate_build([job.xls], cfgs, sites, stops, home=job.home)
    check("validate", rep["ok"], "; ".join(rep.get("errors", [])))
    for w in rep.get("warnings", []):
        warn(w)

    if not road_router.has_graph(DATA):
        check("road graph", False, "missing — download roads first")
        return 1

    picked = list(stops)
    t0 = time.time()
    res = apply_manual_order(job.home, picked, DATA)
    dt_apply = time.time() - t0
    route = res["route"]
    poly = route.get("polyline") or []
    miles = float(route.get("miles") or 0)
    check(
        "apply_manual_order (full pick)",
        len(res["order"]) == len(stops),
        f"{len(res['order'])} stops in {dt_apply:.1f}s",
    )
    check("route polyline + miles", len(poly) >= 2 and miles > 0, f"{miles:.1f} mi, {len(poly)} pts")
    if len(poly) >= 2 and res["order"]:
        last = res["order"][-1]
        clat = last.get("cross_lat", last.get("lat"))
        clon = last.get("cross_lon", last.get("lon"))
        if clat is not None and clon is not None:
            d_tail = math.hypot(poly[-1][0] - float(clat), poly[-1][1] - float(clon))
            check("route ends at last stop", d_tail < 0.03, f"tail delta {d_tail:.4f}")
    if dt_apply > 15:
        warn(f"apply_manual_order took {dt_apply:.1f}s — may feel frozen without spinner")

    half = max(1, len(stops) // 2)
    t0 = time.time()
    finished = auto_finish_order(job.home, stops[:half], stops[half:], DATA)
    check("auto_finish_order", len(finished) == len(stops), f"{len(finished)} stops in {time.time()-t0:.1f}s")
    t0 = time.time()
    res2 = apply_manual_order(job.home, finished, DATA)
    check("apply after auto-finish", len(res2["order"]) == len(stops), f"{time.time()-t0:.1f}s")

    opt = routing.optimize(stops, job.home, DATA)
    check("optimize", len(opt.get("order", [])) == len(stops))

    main_src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    route_src = open(os.path.join(ROOT, "ui", "pages", "route_page.py"), encoding="utf-8").read()
    pick_src = open(os.path.join(ROOT, "ui", "route_pick_dialog.py"), encoding="utf-8").read()
    check("_route_pick_apply handler", "_route_pick_apply" in main_src)
    check("btn_pick_apply wired", "btn_pick_apply" in route_src)
    check("pick dialog apply button", "apply_requested" in pick_src)

    print(f"\n{'=' * 50}")
    print(f"FAIL: {len(FAILURES)}  WARN: {len(WARNS)}")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
        print("\nJOB ROUTE AUDIT FAIL")
        return 1
    print(f"\nJOB ROUTE AUDIT PASS — {job.label} ({job.source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
