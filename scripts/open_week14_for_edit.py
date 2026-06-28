"""Load Week 14: Isaacx pin sites + EST maps + IG TFC install flags + TDS_Report GPS."""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "tds_data")

ISAACX = os.environ.get(
    "TD_WEEK14_XLS",
    r"c:\Users\isaac\Downloads\Week 14 Isaacx.xls",
)
REPORT = os.environ.get(
    "TD_WEEK14_REPORT",
    r"c:\Users\isaac\Downloads\TDS_Report_DEFAULT_2026-06-17 (1).xlsx",
)
IG_TFC = os.environ.get(
    "TD_WEEK14_IG_TFC",
    r"c:\Users\isaac\Downloads\week 14 ig tfc.xlsx",
)
EST_D1 = os.environ.get(
    "TD_WEEK14_EST_D1",
    r"c:\Users\isaac\Downloads\Week 14 Day 1 Isaac (1).est",
)
EST_D2 = os.environ.get(
    "TD_WEEK14_EST_D2",
    r"c:\Users\isaac\Downloads\Week 14 Day 2 Isaac (1).est",
)
FOCUS_SITE = os.environ.get("TD_FOCUS_SITE", "15228").strip()


def build_week14_state(
    *,
    home: tuple[float, float] | None = None,
    focus_site: str = FOCUS_SITE,
) -> tuple[object, int]:
    from core import export, ingest, routing
    from core.map_display import enrich_segment_paths
    from core.state import RouteState
    import road_router

    for path in (ISAACX, REPORT, IG_TFC, EST_D1, EST_D2):
        if not os.path.isfile(path):
            raise FileNotFoundError(path)

    est_cfgs = [
        {"path": EST_D1, "label": "Week 14 Day 1 Isaac"},
        {"path": EST_D2, "label": "Week 14 Day 2 Isaac"},
    ]
    sites = ingest.parse_excel_sites([ISAACX])
    if not sites:
        raise RuntimeError(f"No sites parsed from {ISAACX}")

    if home is None:
        home = (34.12, -117.89)
        for row in sites.values():
            if row.get("lat") is not None:
                home = (float(row["lat"]), float(row["lon"]))
                break

    stops = ingest.match_est_files(est_cfgs, sites, home)
    if not stops:
        raise RuntimeError("EST match returned no stops — check Isaacx + .EST files")

    report = export.parse_report_workbook(REPORT, skip_master=True)
    by_uid = {s["uid"]: s for slist in report.values() for s in slist}
    stops = [ingest.merge_stop_progress(by_uid.get(st["uid"]), st) for st in stops]
    stops = export.apply_ig_tfc_progress(stops, IG_TFC)

    route = {"polyline": [], "miles": 0.0, "legs": [], "graph": False}
    if road_router.has_graph(DATA):
        opt = routing.optimize(list(stops), home, DATA)
        stops = opt["order"]
        route = routing.build_route(stops, home, DATA)

    enrich_segment_paths(stops, DATA)

    st = RouteState(DATA, profile="DEFAULT")
    st.home = home
    st.stops = stops
    st.excel_paths = [ISAACX]
    st.est_paths = [EST_D1, EST_D2]
    st.active_files = [c["label"] for c in est_cfgs]
    st.route = route
    st.offline_mode = False
    st.map_day_filter = "All days"
    st.ig_tfc_path = IG_TFC

    focus_idx = 0
    for i, s in enumerate(st.stops):
        if str(s.get("id")) == focus_site:
            focus_idx = i
    st.current_index = focus_idx

    if not st.save():
        raise RuntimeError("Failed to save tds_backup_DEFAULT.json")

    return st, focus_idx


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Week 14 shift for map + manual GPS")
    parser.add_argument("--no-launch", action="store_true", help="Save state only")
    parser.add_argument(
        "--launch-only",
        action="store_true",
        help="Open START.bat app only (no Excel/route rebuild — use after state is saved)",
    )
    parser.add_argument("--focus", default=FOCUS_SITE, help="Site id to select on Install tab")
    args = parser.parse_args()

    if args.launch_only:
        print("Launching Traffic Deployer (saved shift, no rebuild)…")
        import subprocess

        start_bat = os.path.join(ROOT, "START.bat")
        if os.path.isfile(start_bat):
            subprocess.Popen(["cmd", "/c", start_bat], cwd=ROOT)
        else:
            py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
            subprocess.Popen([py, "main.py"], cwd=ROOT)
        return 0

    focus = args.focus.strip()

    try:
        st, focus_idx = build_week14_state(focus_site=focus)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"FAIL {exc}")
        return 1

    installed = sum(1 for s in st.stops if s.get("installed"))
    field_gps = sum(1 for s in st.stops if s.get("field_lat") is not None)
    missing = [
        str(s.get("id"))
        for s in st.stops
        if s.get("installed") and (s.get("field_lat") is None or s.get("field_lon") is None)
    ]

    print(f"OK  Week 14 loaded — {len(st.stops)} stops on map")
    print(f"    IG TFC installed list + {field_gps} field GPS grabs from TDS_Report")
    print(f"    installed {installed}  route {st.route.get('miles', 0):.1f} mi")
    print(f"    focus site {focus} -> stop #{focus_idx + 1}")
    if missing:
        print(f"    missing field GPS: {', '.join(missing)}")
    print(f"    saved {st.backup_file}")

    if args.no_launch:
        return 0

    print("    launching app…")
    print("    tip: next time use START.bat or --launch-only (skip rebuild)")
    import subprocess

    start_bat = os.path.join(ROOT, "START.bat")
    if os.path.isfile(start_bat):
        subprocess.Popen(["cmd", "/c", start_bat], cwd=ROOT)
    else:
        py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
        subprocess.Popen([py, "main.py"], cwd=ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
