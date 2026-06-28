"""Headless test: Isaac Week 13 Excel + Day 1/2 EST uploads."""
from __future__ import annotations

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "tds_data")
XLS = os.environ.get(
    "TD_WEEK13_XLS",
    r"c:\Users\isaac\Downloads\Week 13 Isaacx.xls",
)
ESTS = [
    (os.environ.get("TD_WEEK13_D1", r"c:\Users\isaac\Downloads\Week 13 Day 1 Isaac.est"), "Day 1"),
    (os.environ.get("TD_WEEK13_D2", r"c:\Users\isaac\Downloads\Week 13 Day 2 Isaac.est"), "Day 2"),
]
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
    print(f"Week 13 upload test — {ROOT}\n")
    from core import ingest, validate, routing
    import road_router

    for p, _ in [(XLS, "xls")] + ESTS:
        check(f"file exists {os.path.basename(p)}", os.path.isfile(p), p)

    sites = ingest.parse_excel_sites([XLS])
    check("parse excel", len(sites) >= 1, f"{len(sites)} sites")

    cfgs = [{"path": p, "label": label} for p, label in ESTS]
    stops = ingest.match_est_files(cfgs, sites, HOME)
    check("est match", len(stops) >= 1, f"{len(stops)} stops")

    by_sheet: dict[str, int] = {}
    for s in stops:
        sh = s.get("sheet") or "?"
        by_sheet[sh] = by_sheet.get(sh, 0) + 1
    print(f"  sheets: {by_sheet}")

    rep = validate.validate_build([XLS], cfgs, sites, stops, home=HOME)
    check("validate", rep["ok"], "; ".join(rep.get("errors", [])))

    if road_router.has_graph(DATA):
        opt = routing.optimize(stops, HOME, DATA)
        ordered = opt["order"]
        check("optimize", len(ordered) == len(stops))
        route = routing.build_route(ordered, HOME, DATA)
        poly = route.get("polyline") or []
        miles = float(route.get("miles") or 0)
        check("build route", len(poly) >= 2 and miles > 0, f"{miles:.1f} mi, {len(poly)} pts")
        if len(poly) >= 2:
            d_home = math.hypot(poly[-1][0] - HOME[0], poly[-1][1] - HOME[1])
            check("route returns home", d_home < 0.02, f"tail delta {d_home:.4f}")
    else:
        print("  WARN no road graph — skip routing")

    if FAILURES:
        print(f"\nWEEK13 FAIL — {len(FAILURES)} check(s)")
        return 1
    print("\nWEEK13 PASS — upload pipeline ready for map + drive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
