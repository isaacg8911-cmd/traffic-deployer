"""Stress test the map route-pick flow on the real Week 16 job (headless, no GPS/counter).

Mirrors the exact Python that a map click triggers:
  JS click -> bridge.onMapClick(lat,lon) -> _on_map_clicked -> _nearest_unpicked_stop
            -> _route_pick_add(uid, side) -> _apply_pick_side -> apply_manual_order

Proves you can select begin/end on every site, in sequence, and apply a real route.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import ingest
from core.map_display import apply_manual_order
from road_router import _haversine_m

DATA = os.path.join(ROOT, "tds_data")
XLS = r"c:\Users\isaac\Downloads\Week 16 Isaacx.xls"
EST = r"c:\Users\isaac\Downloads\Week 16 Day 1 Isaac.est"

FAIL: list[str] = []


def nearest_unpicked(stops, picked, lat, lon, max_m=750.0):
    """Reimplements MapSyncControllerMixin._nearest_unpicked_stop (pure)."""
    best_uid = best_side = None
    best_d = max_m
    for s in stops:
        uid = str(s.get("uid") or "")
        if not uid or uid in picked:
            continue
        for key_lat, key_lon, side in (
            ("begin_lat", "begin_lon", "begin"),
            ("end_lat", "end_lon", "end"),
        ):
            la, lo = s.get(key_lat), s.get(key_lon)
            if la is None or lo is None:
                continue
            d = _haversine_m(lat, lon, float(la), float(lo))
            if d < best_d:
                best_d, best_uid, best_side = d, uid, side
    return best_uid, best_side


def apply_side(stop, side):
    if side == "begin":
        stop["cross_lat"], stop["cross_lon"] = stop["begin_lat"], stop["begin_lon"]
    else:
        stop["cross_lat"], stop["cross_lon"] = stop["end_lat"], stop["end_lon"]
    stop["cross_side"] = side
    stop["pick_cross_locked"] = True


def main() -> int:
    sites = ingest.parse_excel_sites([XLS])
    stops = ingest.match_est_files([{"path": EST, "label": "Day 1"}], sites, (34.34, -119.18))
    print(f"loaded {len(stops)} stops")
    by_uid = {s["uid"]: s for s in stops}

    # Pretend the operator clicks each site, alternating which dot is tapped,
    # exactly on the dot first, then 40 m off (near-miss) to prove tolerance.
    order = sorted(stops, key=lambda s: (float(s["begin_lat"]), float(s["begin_lon"])))
    picked: list[str] = []
    sides: dict[str, str] = {}
    exact_hits = near_hits = 0
    for i, target in enumerate(order):
        want_side = "begin" if i % 2 == 0 else "end"
        la = float(target[f"{want_side}_lat"])
        lo = float(target[f"{want_side}_lon"])
        # alternate exact tap vs ~40 m near-miss (still inside hit tolerance)
        if i % 3 == 0:
            click_la, click_lo = la, lo
            exact = True
        else:
            click_la = la + 0.00035  # ~39 m north
            click_lo = lo
            exact = False
        uid, side = nearest_unpicked(stops, set(picked), click_la, click_lo)
        if uid != target["uid"]:
            FAIL.append(f"click {i} resolved to {uid}, wanted {target['uid']}")
            continue
        if exact:
            exact_hits += 1
        else:
            near_hits += 1
        apply_side(by_uid[uid], side)
        sides[uid] = side
        picked.append(uid)

    print(f"picked {len(picked)}/{len(stops)} (exact taps {exact_hits}, near-miss {near_hits})")
    if len(picked) != len(stops):
        FAIL.append(f"picked {len(picked)} of {len(stops)}")

    ordered = [by_uid[u] for u in picked]
    res = apply_manual_order((34.34, -119.18), ordered, DATA)
    route = res["route"]
    miles = float(route.get("miles") or 0)
    print(f"apply_manual_order: {miles:.1f} mi  graph={route.get('graph')} "
          f"uncovered={route.get('graph_uncovered')} polyline_pts={len(route.get('polyline') or [])}")
    if miles <= 0:
        FAIL.append("route miles not positive")
    if len(res["order"]) != len(stops):
        FAIL.append("apply lost stops")

    print("\n" + "=" * 50)
    if FAIL:
        for f in FAIL:
            print("  FAIL", f)
        print("PICK SIM FAIL")
        return 1
    print("PICK SIM PASS — every begin/end pick (exact + near-miss) landed; route applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
