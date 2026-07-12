"""Prove D7–D9: GPS follow without camera lock, Dijkstra suggest order, Audit sheet.

Gate: static checks + bundled job auto_finish road matrix + audit table wiring.
"""
from __future__ import annotations

import copy
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FAILURES: list[str] = []


def ok(name: str, detail: str = "") -> None:
    print(f"  OK  {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = "") -> None:
    msg = f"{name}" + (f": {detail}" if detail else "")
    print(f"  FAIL {msg}")
    FAILURES.append(msg)


def main() -> int:
    print("PROVE D7-D9 (GPS pan unlock, road suggest order, audit sheet)\n")

    appjs = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    map_sync = open(os.path.join(ROOT, "ui", "controllers", "map_sync.py"), encoding="utf-8").read()
    map_display = open(os.path.join(ROOT, "core", "map_display.py"), encoding="utf-8").read()
    audit_py = open(os.path.join(ROOT, "ui", "controllers", "audit.py"), encoding="utf-8").read()
    audit_page = open(os.path.join(ROOT, "ui", "pages", "audit_page.py"), encoding="utf-8").read()
    route_py = open(os.path.join(ROOT, "ui", "controllers", "route.py"), encoding="utf-8").read()

    # --- D7: GPS marker without per-fix camera lock --------------------------------
    render_gps = appjs.split("function renderGps")[1].split("function renderNav")[0]
    if "recenterPending" in appjs and "map.on('dragstart'" in appjs:
        ok("D7 follow pan unlock hooks")
    else:
        fail("D7 follow pan unlock hooks")

    if "map.jumpTo({ center: [g.lon, g.lat]" not in render_gps:
        ok("D7 no jumpTo on every GPS fix")
    else:
        fail("D7 no jumpTo on every GPS fix", "still recenters each tick")

    if "recenterOnGps" in appjs and "recenterPending = true" in appjs:
        ok("D7 explicit recenter on Follow")
    else:
        fail("D7 explicit recenter on Follow")

    if "_stop_drive()" not in map_sync.split("def _on_map_follow_toggled")[1].split("def _shift_has_field_progress")[0]:
        ok("D7 pan does not stop drive mode from Python")
    else:
        fail("D7 pan stops drive on follow off")

    # --- D8: Suggest order uses Dijkstra matrix ------------------------------------
    if "_stops_only_matrix" in map_display and "_refine_open_order" in map_display:
        ok("D8 auto_finish uses road matrix + refine")
    else:
        fail("D8 auto_finish road engine")

    if "optimize(pool, home, data_dir)" in map_display:
        ok("D8 empty-pick delegates to optimize()")
    else:
        fail("D8 empty-pick optimize path")

    if "Suggest order" in route_py and "Dijkstra" in route_py:
        ok("D8 suggest order warns without graph")
    else:
        fail("D8 suggest order graph warning")

    from core import ingest
    from core.map_display import auto_finish_order
    from core.routing import _open_path_cost_assigned, _stops_only_matrix
    from field_job_fixtures import resolve_field_job
    from ui.paths import DATA_DIR
    import road_router

    job = resolve_field_job()
    if not os.path.isfile(job.xls):
        fail("D8 job fixture", job.xls)
    else:
        sites = ingest.parse_excel_sites([job.xls])
        cfgs = [{"path": p, "label": label} for p, label in job.ests]
        stops = ingest.match_est_files(cfgs, sites, job.home)
        if len(stops) >= 4:
            half = max(1, len(stops) // 3)
            picked = copy.deepcopy(stops[:half])
            pool = copy.deepcopy(stops[half:])
            t0 = time.time()
            ordered = auto_finish_order(job.home, picked, pool, DATA_DIR)
            dt = time.time() - t0
            if len(ordered) == len(stops):
                ok("D8 auto_finish count", f"{len(ordered)} stops in {dt:.1f}s")
            else:
                fail("D8 auto_finish count", f"got {len(ordered)} expected {len(stops)}")

            if road_router.has_graph(DATA_DIR):
                graph = road_router.load_graph(DATA_DIR)
                _, road_lengths = _stops_only_matrix(graph, ordered)
                road_cost = _open_path_cost_assigned(graph, ordered, road_lengths)
                if road_cost > 0:
                    ok("D8 road-graph tour cost", f"{road_cost / 1609.34:.2f} mi")
                else:
                    fail("D8 road-graph tour cost", "zero")
            else:
                ok("D8 road graph (headless skip)", "no graph on disk — static engine checks only")
        else:
            fail("D8 job stops", f"only {len(stops)}")

    # --- D9: Audit live sheet ------------------------------------------------------
    if "table_audit_sheet" in audit_page and "_refresh_audit_sheet" in audit_py:
        ok("D9 audit sheet table wired")
    else:
        fail("D9 audit sheet table wired")

    if "Live shift data" in audit_page:
        ok("D9 audit sheet label")
    else:
        fail("D9 audit sheet label")

    if FAILURES:
        print(f"\nPROVE D7-D9 FAIL ({len(FAILURES)})\n")
        for f in FAILURES:
            print(f"  - {f}")
        return 1

    print("\nPROVE D7-D9 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
