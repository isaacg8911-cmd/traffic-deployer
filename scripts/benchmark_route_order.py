"""Week 14 (or any week): prove open-path route miles site1->last (home excluded)."""
from __future__ import annotations

import copy
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "tds_data")
HOME = (
    float(os.environ.get("TD_JOB_HOME_LAT", "33.7715")),
    float(os.environ.get("TD_JOB_HOME_LON", "-117.9431")),
)
XLS = os.environ.get(
    "TD_WEEK14_XLS",
    os.environ.get("TD_JOB_XLS", r"c:\Users\isaac\Downloads\Week 14 Isaacx.xls"),
)
EST_ENV = os.environ.get("TD_WEEK14_EST", os.environ.get("TD_JOB_EST", "")).strip()
if EST_ENV:
    ESTS = []
    for chunk in EST_ENV.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        base = os.path.basename(chunk)
        label = base.split(" Day ")[-1].replace(".est", "").strip() if " Day " in base else base
        if not label or label == base:
            label = f"Map {len(ESTS) + 1}"
        ESTS.append((chunk, label))
else:
    ESTS = [
        (
            os.environ.get(
                "TD_WEEK14_D1",
                r"c:\Users\isaac\Downloads\Week 14 Day 1 Isaac.est",
            ),
            "Day 1",
        ),
        (
            os.environ.get(
                "TD_WEEK14_D2",
                r"c:\Users\isaac\Downloads\Week 14 Day 2 Isaac.est",
            ),
            "Day 2",
        ),
    ]


def main() -> int:
    from core import ingest, routing
    from core.maps_links import nav_coords
    import road_router

    for p, _ in [(XLS, "xls")] + ESTS:
        if not os.path.isfile(p):
            print(f"MISSING: {p}")
            return 1

    sites = ingest.parse_excel_sites([XLS])
    cfgs = [{"path": p, "label": label} for p, label in ESTS]
    stops = ingest.match_est_files(cfgs, sites, HOME)
    print(f"Open-path benchmark — {len(stops)} stops")
    by_sheet: dict[str, int] = {}
    for s in stops:
        sh = s.get("sheet") or "?"
        by_sheet[sh] = by_sheet.get(sh, 0) + 1
    print(f"  sheets: {by_sheet}")

    if not road_router.has_graph(DATA):
        print("FAIL — no road graph in tds_data (download map first)")
        return 1

    t0 = time.time()
    opt = routing.optimize(copy.deepcopy(stops), HOME, DATA)
    ordered = opt["order"]
    route = routing.build_route(ordered, HOME, DATA)
    miles = float(route.get("miles") or 0.0)
    elapsed = time.time() - t0

    print("\n=== Site 1 -> site N (you drive to site 1; home not in route) ===")
    print(f"  site1->last miles: {miles:.1f} mi")
    print(f"  compute:           {elapsed:.1f}s")
    print(f"  stops:             {len(ordered)}")

    pts = []
    for stop in ordered[:10]:
        c = nav_coords(stop)
        if c:
            pts.append(f"{c[0]:.6f},{c[1]:.6f}")
    if pts:
        print("\nGoogle Maps chain (first 10 stops):")
        print("  https://www.google.com/maps/dir/" + "/".join(pts))

    print("\nFirst 8 stops:")
    for i, s in enumerate(ordered[:8], start=1):
        c = nav_coords(s)
        ctxt = f"{c[0]:.5f},{c[1]:.5f}" if c else "?"
        print(f"  #{i} Site {s.get('id')} — {str(s.get('street', ''))[:40]}  ({ctxt})")

    if len(ordered) >= 2:
        print(f"\nLast stop: #{len(ordered)} Site {ordered[-1].get('id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
