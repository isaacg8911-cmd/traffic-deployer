"""Manual route pick — locked begin/end, no auto-finish on apply (work-laptop UX proof)."""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "tds_data")
FAILURES: list[str] = []


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


def _locked_stop(base: dict, side: str) -> dict:
    s = copy.deepcopy(base)
    s["pick_cross_locked"] = True
    s["cross_side"] = side
    if side == "begin":
        s["cross_lat"] = s["begin_lat"]
        s["cross_lon"] = s["begin_lon"]
    else:
        s["cross_lat"] = s["end_lat"]
        s["cross_lon"] = s["end_lon"]
    return s


def main() -> int:
    print("Manual pick flow — source + routing proof\n")

    from field_job_fixtures import resolve_field_job
    from core import ingest
    from core.map_display import apply_manual_order
    from core.routing import _assign_crossings
    import road_router

    job = resolve_field_job()
    cfgs = [{"path": p, "label": label} for p, label in job.ests]
    sites = ingest.parse_excel_sites([job.xls])
    stops = ingest.match_est_files(cfgs, sites, job.home)
    check("bundled job stops", len(stops) >= 2, f"{len(stops)}")

    # --- Source markers (must ship in frozen bundle after rebuild) ---
    main_src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    appjs = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    threads_src = open(os.path.join(ROOT, "ui", "threads.py"), encoding="utf-8").read()
    routing_src = open(os.path.join(ROOT, "core", "routing.py"), encoding="utf-8").read()

    for needle, where in (
        ("_enter_pick_map_focus", "main.py map-first pick layout"),
        ("_parse_stop_click", "main.py begin|end click payload"),
        ("pick_cross_locked", "main.py locked crossing"),
        ("pick_waiting", "main.py map banner hint"),
        ("kind: 'begin'", "app.js always show begin/end"),
        ("pick_waiting", "app.js map banner"),
        ("pick_sides", "threads.py apply respects sides"),
        ("pick_cross_locked", "routing.py honor locked side"),
    ):
        src = main_src if "main.py" in where else appjs if "app.js" in where else threads_src if "threads" in where else routing_src
        check(where, needle in src, needle)

    # --- Locked side routing ---
    s0, s1 = stops[0], stops[1]
    ordered = [_locked_stop(s0, "begin"), _locked_stop(s1, "end")]
    if road_router.has_graph(DATA):
        graph = road_router.load_graph(DATA)
        out = _assign_crossings(graph, job.home, copy.deepcopy(ordered))
        check(
            "locked begin kept",
            out[0]["cross_side"] == "begin"
            and abs(float(out[0]["cross_lat"]) - float(s0["begin_lat"])) < 1e-6,
        )
        check(
            "locked end kept",
            out[1]["cross_side"] == "end"
            and abs(float(out[1]["cross_lat"]) - float(s1["end_lat"])) < 1e-6,
        )
        res = apply_manual_order(job.home, ordered, DATA)
        check(
            "apply_manual_order locked sides",
            len(res["order"]) == 2 and float(res["route"].get("miles") or 0) > 0,
            f"{res['route'].get('miles', 0):.1f} mi",
        )
    else:
        check("road graph", False, "missing — download roads on creator PC")

    # --- Apply thread rejects partial pick (no auto-finish) ---
    from ui.threads import RouteApplyPickThread

    thread = RouteApplyPickThread(
        job.home,
        [stops[0]["uid"]],
        stops,
        DATA,
        pick_sides={stops[0]["uid"]: "begin"},
    )
    result: dict = {}

    def capture(res: dict):
        result.update(res)

    thread.finished_result.connect(capture)
    thread.run()
    check(
        "partial pick rejected",
        not result.get("ok") and "Pick all" in str(result.get("error", "")),
        str(result.get("error", ""))[:60],
    )

    print(f"\n{'=' * 50}")
    print(f"FAIL: {len(FAILURES)}")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
        print("\nMANUAL PICK TEST FAIL")
        return 1
    print("\nMANUAL PICK TEST PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
