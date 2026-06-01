"""Headless smoke suite — run after every change: python scripts/smoke_full.py"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA_DIR = os.path.join(ROOT, "tds_data")
WEB_DIR = os.path.join(ROOT, "web")
FAILURES: list[str] = []


def ok(name: str):
    print(f"  OK  {name}")


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        ok(name)
    else:
        msg = f"  FAIL {name}" + (f": {detail}" if detail else "")
        print(msg)
        FAILURES.append(name if not detail else f"{name}: {detail}")


def test_imports():
    print("[imports]")
    from core import export, ingest, routing, validate, tvp_import  # noqa: F401
    from core.state import RouteState
    import bridge
    import gps_reader
    import local_server
    import main
    import persistence
    import road_router
    import voice_nav
    from version import APP_NAME, APP_VERSION
    check("core modules", True)
    check("version", APP_NAME == "Traffic Deployer" and APP_VERSION)
    ok(f"version {APP_VERSION}")


def test_validate_merge():
    print("[validate / ingest]")
    from core import ingest, validate
    r = validate.validate_build([], [], {}, [])
    check("validate rejects empty build", not r["ok"])
    old = ingest.new_stop("12", "Day1", {
        "street": "Main St", "begin_lat": 33.77, "begin_lon": -117.94,
        "end_lat": 33.78, "end_lon": -117.95, "lat": 33.775, "lon": -117.945,
    })
    old["installed"] = True
    old["field_lat"] = 33.776
    fresh = ingest.new_stop("12", "Day1", {
        "street": "Site 12", "begin_lat": 33.77, "begin_lon": -117.94,
        "end_lat": 33.78, "end_lon": -117.95, "lat": 33.775, "lon": -117.945,
    })
    m = ingest.merge_stop_progress(old, fresh)
    check("merge keeps install + field GPS", m["installed"] and m["field_lat"] == 33.776)
    check("merge keeps street name", m["street"] == "Main St")


def test_persistence():
    print("[persistence]")
    import persistence
    d = tempfile.mkdtemp()
    p = os.path.join(d, "tds_backup_SMOKE.json")
    payload = {"profile": "SMOKE", "stops": [{"id": "1"}], "home": [33.77, -117.94]}
    check("save_state", persistence.save_state(payload, p, d))
    back = persistence.load_state(p, d)
    check("load round-trip", back.get("profile") == "SMOKE" and len(back.get("stops", [])) == 1)


def test_export():
    print("[export]")
    from core import export
    stops = [{
        "id": "7", "sheet": "Day1", "street": "Main St", "serial": "ABC",
        "direction": "n", "lanes": 2, "installed": True, "field_lat": 33.77,
        "field_lon": -117.94, "cross_lat": 33.771, "cross_lon": -117.941,
        "date": "2026-05-31", "exact_time": "2026-05-31 12:00:00",
    }]
    aud = export.audit(stops)
    check("audit pass with serial", aud["ok"])
    xlsx = export.to_excel_bytes(stops)
    check("excel export bytes", xlsx is not None and len(xlsx) > 500)
    csv = export.to_csv_text(stops)
    check("csv export", "Main St" in csv and "ABC" in csv)
    path = export.default_report_path(DATA_DIR, "SMOKE", "xlsx")
    check("export default path", path.endswith(".xlsx") and "exports" in path)
    check("export dir exists", os.path.isdir(export.export_dir(DATA_DIR)))


def test_demo_data():
    print("[demo data]")
    demo_csv = os.path.join(ROOT, "demo_data", "demo_sites.csv")
    demo_est = os.path.join(ROOT, "demo_data", "DemoDay.EST")
    check("demo csv", os.path.isfile(demo_csv))
    check("demo est", os.path.isfile(demo_est))
    from core import ingest
    sites = ingest.parse_excel_sites([demo_csv])
    check("demo sites parsed", len(sites) >= 5, f"got {len(sites)}")
    cfgs = [{"path": demo_est, "label": "DemoDay"}]
    stops = ingest.match_est_files(cfgs, sites, (33.7715, -117.9431))
    check("demo est match", len(stops) >= 5, f"matched {len(stops)}")


def test_voice():
    print("[voice]")
    import voice_nav
    check("maneuver phrase", voice_nav.maneuver_phrase("left", "Papaya St") ==
          "Turn left onto Papaya Street.")
    check("female voice only", voice_nav.normalize_voice_style("vader") == "female")
    check("pyttsx3 import", voice_nav.tts_available(), voice_nav.tts_error() or "missing")


def test_web_assets():
    print("[web assets]")
    style = open(os.path.join(WEB_DIR, "style.js"), encoding="utf-8").read()
    appjs = open(os.path.join(WEB_DIR, "app.js"), encoding="utf-8").read()
    idx = open(os.path.join(WEB_DIR, "index.html"), encoding="utf-8").read()
    check("style glyphs", "glyphs:" in style)
    check("style buildings", "buildings-fill" in style)
    check("no address clutter", "address-labels" not in style)
    check("follow street zoom", "FOLLOW_ZOOM = 13" in appjs)
    check("nav banner html", "navbar" in idx and "nav-arrow" in idx)
    for rel in ("vendor/maplibre-gl.js", "vendor/pmtiles.js", "style.js", "app.js"):
        check(f"file {rel}", os.path.isfile(os.path.join(WEB_DIR, rel)))


def test_local_server():
    print("[local server]")
    import local_server
    port = local_server.start(WEB_DIR, DATA_DIR)
    check("server port", port > 0)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=5) as r:
            body = r.read(8000).decode("utf-8", errors="replace")
        check("index served", "Traffic Deployer Map" in body)
        check("app.js linked", "app.js" in body)
        font_url = f"http://127.0.0.1:{port}/vendor/fonts/Noto%20Sans%20Regular/0-255.pbf"
        with urllib.request.urlopen(font_url, timeout=5) as fr:
            fb = fr.read(200)
        check("label font served", len(fb) > 50)
    except Exception as exc:
        check("index served", False, str(exc))
    local_server.stop()


def test_basemap():
    print("[basemap]")
    pmtiles = os.path.join(DATA_DIR, "california.pmtiles")
    fonts = os.path.join(WEB_DIR, "vendor", "fonts", "Noto Sans Regular", "0-255.pbf")
    if os.path.isfile(pmtiles):
        mb = os.path.getsize(pmtiles) / (1024 * 1024)
        ok(f"california.pmtiles ({mb:.0f} MB)")
    else:
        print("  WARN california.pmtiles missing — run setup_maps.py once")
    check("label fonts", os.path.isfile(fonts))


def test_routing():
    print("[routing]")
    import road_router
    d = road_router.dist_to_polyline_m(33.77, -117.94, [[33.77, -117.94], [33.78, -117.95]])
    check("dist_to_polyline", 0 <= d < 5)
    if road_router.has_graph(DATA_DIR):
        g = road_router.load_graph(DATA_DIR)
        start = (33.7715, -117.9431)
        dest = (33.85, -117.88)  # far enough for a real multi-node leg on the saved graph
        leg = road_router.leg_plan(g, start, dest, stop_index=0)
        check("leg_plan ok", leg.get("ok") and len(leg.get("maneuvers", [])) >= 2)
        plan = road_router.nav_plan(g, [start, dest])
        types = [m["type"] for m in plan.get("plan", [])]
        check("nav_plan has depart+arrive", "depart" in types and "arrive" in types)
        check("nav_plan legs", len(plan.get("legs", [])) == 1)
        ok(f"road graph ({len(g.nodes)} nodes)")
    else:
        print("  WARN road_graph.graphml missing — download road map in Setup for full routing")


def test_state_voice_persist():
    print("[state prefs]")
    from core.state import RouteState
    d = tempfile.mkdtemp()
    st = RouteState(d, profile="SMOKE")
    st.voice_nav = True
    st.voice_style = "female"
    st.save()
    st2 = RouteState(d, profile="SMOKE")
    check("voice_style saved", st2.load() and st2.voice_style == "female")


def test_field_ready():
    print("[field readiness]")
    from core.field_ready import check_all
    r = check_all(ROOT, probe_gps=False, stop_server_after=True)
    check("field_ready score", r["score"] >= 82, f"score={r['score']}")
    check("basemap ok", any(i["id"] == "basemap" and i["ok"] for i in r["items"]))
    check("map server ok", any(i["id"] == "server" and i["ok"] for i in r["items"]))
    ok(f"readiness {r['score']}/100 ({r['warn_count']} warn, {r['fail_count']} fail)")


def main() -> int:
    print(f"Traffic Deployer smoke_full — {ROOT}\n")
    test_imports()
    test_validate_merge()
    test_persistence()
    test_export()
    test_demo_data()
    test_voice()
    test_web_assets()
    test_local_server()
    test_basemap()
    test_routing()
    test_state_voice_persist()
    test_field_ready()
    print()
    if FAILURES:
        print(f"SMOKE FAILED ({len(FAILURES)}):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("SMOKE PASS — all checks green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
