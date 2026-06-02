"""Download road_graph.graphml from the command line (work-laptop friendly).

Examples:
  cd C:\\TrafficDeployer
  .venv\\Scripts\\python.exe scripts\\download_road_map.py --demo

  .venv\\Scripts\\python.exe scripts\\download_road_map.py ^
    --excel "C:\\jobs\\sites.xlsx" --est "C:\\jobs\\Day5.EST" ^
    --home 34.05 -118.25
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA_DIR = os.path.join(ROOT, "tds_data")
DEMO_CSV = os.path.join(ROOT, "demo_data", "demo_sites.csv")
DEMO_EST = os.path.join(ROOT, "demo_data", "DemoDay.EST")


def _gather(excel: list[str], est: list[str], home: tuple[float, float]) -> list[list[float]]:
    from core import ingest

    pts: list[list[float]] = [list(home)]
    if excel and est:
        sites = ingest.parse_excel_sites(excel)
        cfgs = [{"path": p, "label": os.path.splitext(os.path.basename(p))[0]} for p in est]
        stops = ingest.match_est_files(cfgs, sites, home)
        for s in stops:
            pts.append([s["begin_lat"], s["begin_lon"]])
            pts.append([s["end_lat"], s["end_lon"]])
    return pts


def main() -> int:
    ap = argparse.ArgumentParser(description="Download offline road routing graph (Overpass).")
    ap.add_argument("--demo", action="store_true", help="Use demo_data (desk test)")
    ap.add_argument("--excel", action="append", default=[], help="Excel/CSV path (repeatable)")
    ap.add_argument("--est", action="append", default=[], help=".EST path (repeatable)")
    ap.add_argument("--home", nargs=2, type=float, metavar=("LAT", "LON"), help="Start lat lon")
    args = ap.parse_args()

    if args.demo:
        excel, est = [DEMO_CSV], [DEMO_EST]
        home = (34.11864, -117.919266)
    else:
        excel, est = args.excel, args.est
        if not excel or not est or not args.home:
            ap.error("Need --excel, --est, and --home (or use --demo).")
        home = (float(args.home[0]), float(args.home[1]))

    import road_router

    if not road_router.HAS_ROUTING:
        print("FAIL: osmnx not installed. Run START.bat once.")
        return 1

    pts = _gather(excel, est, home)
    if len(pts) < 2:
        print("FAIL: no site points (check Excel + .EST).")
        return 1

    w, s, e, n, span = road_router.bbox_for_points(pts)
    print(f"Work area ~{span:.1f} mi  bbox W={w:.4f} S={s:.4f} E={e:.4f} N={n:.4f}")

    hint = road_router.probe_roads_internet()
    if hint:
        print(f"WARN: {hint}")
        print("Continuing anyway...\n")

    try:
        info = road_router.download_area(pts, DATA_DIR)
    except Exception as exc:  # noqa: BLE001
        print(f"\nFAIL: {exc}")
        print("\nTry: phone hotspot on this laptop, then run this script again.")
        return 1

    print(
        f"\nOK: {info['nodes']} nodes, {info.get('named_edges', 0)} named edges, "
        f"~{info['radius_mi']} mi span"
    )
    print(f"Saved: {road_router.graph_path(DATA_DIR)}")
    print("In the app: BUILD OPTIMIZED ROUTE, then Refresh check on Setup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
