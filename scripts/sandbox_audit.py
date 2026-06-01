"""Workflow sandbox — exercises every major path without the GUI."""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DATA = os.path.join(ROOT, "tds_data")
WEB = os.path.join(ROOT, "web")

FAILS: list[str] = []
WARNS: list[str] = []
OKS: list[str] = []


def ok(msg): OKS.append(msg); print(f"  OK  {msg}")
def warn(msg): WARNS.append(msg); print(f"  WARN {msg}")
def fail(msg): FAILS.append(msg); print(f"  FAIL {msg}")


def section(title):
    print(f"\n[{title}]")


def test_synthetic_workflow():
    """Simulate: upload → validate → route state → install → export."""
    section("synthetic shift workflow")
    from core import ingest, validate, export
    from core.state import RouteState, ca_now

    sites = {
        "101": {"begin_lat": 33.77, "begin_lon": -117.94, "end_lat": 33.78, "end_lon": -117.95,
                "lat": 33.775, "lon": -117.945, "street": "Main St"},
        "102": {"begin_lat": 33.80, "begin_lon": -117.90, "end_lat": 33.81, "end_lon": -117.91,
                "lat": 33.805, "lon": -117.905, "street": "Oak Ave"},
    }
    est_cfgs = [{"label": "Day1", "path": "fake.est", "text": "101 102"}]
    stops_raw = ingest.match_est_files(est_cfgs, sites, (33.7715, -117.9431))
    if len(stops_raw) < 2:
        fail(f"ingest matched {len(stops_raw)} stops (expected 2)")
    else:
        ok(f"ingest matched {len(stops_raw)} stops")

    rep = validate.validate_build(["fake.xlsx"], est_cfgs, sites, stops_raw)
    ok("validate passes synthetic build") if rep["ok"] else fail(f"validate: {rep['errors']}")

    td, _ = ca_now()
    d = tempfile.mkdtemp()
    st = RouteState(d, profile="SANDBOX")
    st.stops = [ingest.merge_stop_progress(None, s) for s in stops_raw]
    st.home = (33.7715, -117.9431)
    for s in st.stops:
        s["date"] = td
    st.save()
    st2 = RouteState(d, profile="SANDBOX")
    ok("state save/load") if st2.load() and len(st2.stops) == 2 else fail("state round-trip")

    # install one, skip one
    st2.stops[0]["installed"] = True
    st2.stops[0]["serial"] = "SN-001"
    st2.stops[0]["field_lat"] = 33.776
    st2.stops[0]["field_lon"] = -117.944
    st2.stops[0]["direction"] = "n"
    st2.stops[1]["skipped"] = True
    st2.save()

    aud = export.audit(st2.stops)
    ok("audit ok with serial") if aud["ok"] else fail(f"audit: {aud['missing']}")
    xlsx = export.to_excel_bytes(st2.stops)
    ok("excel export") if xlsx and len(xlsx) > 500 else fail("excel export empty")


def test_routing_paths():
    section("routing paths")
    import road_router
    if not road_router.has_graph(DATA):
        warn("no road graph — route/drive paths untested offline")
        return
    g = road_router.load_graph(DATA)
    import networkx as nx
    from core import routing

    # optimize needs stops with segment geometry
    stops = [{
        "uid": "a", "id": "1", "sheet": "D1",
        "begin_lat": 33.77, "begin_lon": -117.94, "end_lat": 33.78, "end_lon": -117.95,
        "lat": 33.775, "lon": -117.945,
    }, {
        "uid": "b", "id": "2", "sheet": "D1",
        "begin_lat": 33.85, "begin_lon": -117.88, "end_lat": 33.86, "end_lon": -117.87,
        "lat": 33.855, "lon": -117.875,
    }]
    try:
        res = routing.optimize(stops, (33.7715, -117.9431), DATA)
        ok(f"optimize order ({len(res.get('order', []))} stops)")
    except Exception as exc:
        fail(f"optimize: {exc}")

    try:
        route = routing.build_route(stops, (33.7715, -117.9431), DATA)
        ok(f"build_route miles={route.get('miles', 0):.2f} graph={route.get('graph')}")
    except Exception as exc:
        fail(f"build_route: {exc}")


def test_ui_wiring():
    section("UI / bridge wiring")
    import inspect
    import main as appmod
    mw = appmod.MainWindow
    handlers = [
        "_page_setup", "_page_route", "_page_install", "_page_pickup", "_page_audit",
        "_toggle_drive", "_start_drive", "_stop_drive", "_nav_update",
        "_grab_gps_here", "_mark_installed", "_mark_skipped", "_export_excel",
        "_build_route_from_uploads", "_download_roads", "_ready_offline",
        "_refresh_field_ready", "_run_smoke_test", "_show_about",
        "_on_voice_toggle", "_on_voice_style_changed",
    ]
    for h in handlers:
        ok(h) if hasattr(mw, h) else fail(f"missing handler {h}")

    bridge_src = open(os.path.join(ROOT, "bridge.py"), encoding="utf-8").read()
    for fn in ("send_state", "send_gps", "send_nav", "send_drive_leg", "fly_to", "set_follow"):
        ok(f"bridge.{fn}") if fn in bridge_src else fail(f"bridge missing {fn}")

    appjs = open(os.path.join(WEB, "app.js"), encoding="utf-8").read()
    for fn in ("__tdPushState", "__tdPushGps", "__tdPushNav", "__tdSetDriveLeg", "__tdFlyTo"):
        ok(f"app.js {fn}") if fn in appjs else fail(f"app.js missing {fn}")


def test_gps_module():
    section("GPS module")
    import gps_reader
    st = gps_reader.get_status(attempts=2)
    if st.get("connected"):
        ok("GPS hardware detected") if st.get("fix") else warn("GPS connected, no fix (normal indoors)")
    else:
        warn("GPS not connected — field test needed")


def test_voice_paths():
    section("voice")
    import voice_nav
    v = voice_nav.NavVoice()
    ok("NavVoice init") if v.ready or voice_nav.tts_available() else warn("voice engine slow/start")
    ann = voice_nav.DriveVoiceAnnouncer(v)
    ann.reset()
    ok("DriveVoiceAnnouncer")


def test_edge_cases():
    section("edge cases")
    import road_router
    if road_router.has_graph(DATA):
        g = road_router.load_graph(DATA)
        # same-node leg (close stops)
        leg = road_router.leg_plan(g, (33.7715, -117.9431), (33.7716, -117.9430), 0)
        types = [m["type"] for m in leg.get("maneuvers", [])]
        ok("close-stop leg has depart+arrive") if "depart" in types and "arrive" in types else fail(f"leg types: {types}")
        off = road_router.dist_to_polyline_m(33.77, -117.94, [[33.78, -117.95], [33.79, -117.96]])
        ok("off-route distance") if off > 1000 else fail(f"off-route too small: {off}")


def test_missing_polish():
    section("polish gaps (code review)")
    gaps = []
    if not os.path.isfile(os.path.join(ROOT, "demo_data", "sample_sites.csv")):
        gaps.append("no bundled demo dataset for desk testing")
    if not os.path.isfile(os.path.join(ROOT, "TrafficDeployer.spec")):
        gaps.append("no PyInstaller .exe (requires Python visible)")
    main_src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    if "Undo" not in main_src and "undo" not in main_src.lower():
        gaps.append("no undo for accidental SKIP/INSTALL")
    if "keyboard" not in main_src.lower() and "shortcut" not in main_src.lower():
        gaps.append("no keyboard shortcuts for Install tab (field gloves)")
    for g in gaps:
        warn(g)


def main():
    print("Traffic Deployer — sandbox audit\n")
    test_synthetic_workflow()
    test_routing_paths()
    test_ui_wiring()
    test_gps_module()
    test_voice_paths()
    test_edge_cases()
    test_missing_polish()
    print(f"\n{'='*50}")
    print(f"OK: {len(OKS)}  WARN: {len(WARNS)}  FAIL: {len(FAILS)}")
    if FAILS:
        print("\nFailures:")
        for f in FAILS:
            print(f"  - {f}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
