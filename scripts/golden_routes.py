"""Golden route mile bands — regression guard for routing changes (P35).

    .venv\\Scripts\\python.exe scripts\\golden_routes.py
"""
from __future__ import annotations

import copy
import json
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
BANDS_FILE = os.path.join(ROOT, "demo_data", "golden_route_bands.json")

# Wide bands — catch gross regressions only.
DEFAULT_BANDS = {
    "demo": {"stops": 5, "miles_min": 5.0, "miles_max": 120.0, "budget_s": 60},
    "n20": {"stops": 20, "miles_min": 3.0, "miles_max": 80.0, "budget_s": 120},
    "n40": {"stops": 40, "miles_min": 3.0, "miles_max": 80.0, "budget_s": 180},
}


def _load_demo_stops():
    from core import ingest

    sites = ingest.parse_excel_sites([DEMO_CSV])
    cfgs = [{"path": DEMO_EST, "label": "DemoDay"}]
    return ingest.match_est_files(cfgs, sites, HOME)


def _expand(base: list, count: int) -> list:
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


def _run(stops: list) -> tuple[float, float, bool]:
    from core import routing
    import road_router

    if not road_router.has_graph(DATA):
        return 0.0, 0.0, False
    t0 = time.perf_counter()
    opt = routing.optimize(stops, HOME, DATA)
    route = routing.build_route(opt["order"], HOME, DATA)
    elapsed = time.perf_counter() - t0
    miles = float(route.get("miles") or 0)
    ok = bool(route.get("graph")) and miles > 0.1 and len(route.get("polyline") or []) >= 4
    return miles, elapsed, ok


def load_bands() -> dict:
    if os.path.isfile(BANDS_FILE):
        with open(BANDS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return dict(DEFAULT_BANDS)


def verify(*, update: bool = False) -> tuple[bool, list[str]]:
    import road_router

    if not road_router.has_graph(DATA):
        return False, ["no road_graph.graphml in tds_data"]
    base = _load_demo_stops()
    bands = load_bands()
    msgs: list[str] = []
    all_ok = True
    cases = (
        ("demo", base),
        ("n20", _expand(base, 20)),
        ("n40", _expand(base, 40)),
    )
    for key, stops in cases:
        spec = bands.get(key, DEFAULT_BANDS[key])
        miles, elapsed, ok = _run(stops)
        if not ok:
            all_ok = False
            msgs.append(f"{key}: route build failed")
            continue
        if update:
            spec = dict(spec)
            spec["miles_min"] = round(max(1.0, miles * 0.6), 1)
            spec["miles_max"] = round(miles * 1.5 + 5, 1)
            spec["budget_s"] = max(60, int(elapsed * 2.5))
            bands[key] = spec
        lo, hi = float(spec["miles_min"]), float(spec["miles_max"])
        budget = float(spec.get("budget_s", 120))
        mile_ok = lo <= miles <= hi
        time_ok = elapsed <= budget
        if not mile_ok or not time_ok:
            all_ok = False
        msgs.append(
            f"{key}: {miles:.1f} mi in {elapsed:.1f}s "
            f"(band {lo}-{hi} mi, budget {budget:.0f}s) "
            f"{'OK' if mile_ok and time_ok else 'FAIL'}"
        )
    if update:
        os.makedirs(os.path.dirname(BANDS_FILE), exist_ok=True)
        with open(BANDS_FILE, "w", encoding="utf-8") as f:
            json.dump(bands, f, indent=2)
        msgs.append(f"Updated {BANDS_FILE}")
    return all_ok, msgs


def main() -> int:
    update = "--update" in sys.argv
    ok, msgs = verify(update=update)
    for m in msgs:
        print(m)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
