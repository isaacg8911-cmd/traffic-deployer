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


def test_export_audit_counter():
    print("[export audit]")
    from core import export

    stops = [{
        "id": 12,
        "installed": True,
        "picked_up": True,
        "counter_unit_id": "1234nc1b",
        "serial": "x",
        "street": "Main",
    }]
    r = export.audit(stops)
    check("audit flags missing counter download", not r["ok"])
    check("audit counter download msg", any("download" in m.lower() for m in r["missing"]))


def test_shift_summary():
    print("[shift summary]")
    from core.shift_summary import summarize

    s = summarize([], None)
    check("empty shift", s["installed"] == 0 and "No stops" in s["text"])
    s2 = summarize(
        [{"installed": True, "counter_unit_id": "1234nc1b", "counter_download_path": "x.pcbin"}],
        {"miles": 12.0},
    )
    check("shift counter line", "PicoCount" in s2["text"])


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
    xlsx, xlsx_err = export.to_excel_result(stops)
    check("excel export bytes", xlsx is not None and len(xlsx) > 500, xlsx_err or "")
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


def test_web_assets():
    print("[web assets]")
    style = open(os.path.join(WEB_DIR, "style.js"), encoding="utf-8").read()
    appjs = open(os.path.join(WEB_DIR, "app.js"), encoding="utf-8").read()
    idx = open(os.path.join(WEB_DIR, "index.html"), encoding="utf-8").read()
    check("style glyphs", "glyphs:" in style)
    check("style buildings", "buildings-fill" in style)
    check("no address clutter", "address-labels" not in style)
    check("follow street zoom", "FOLLOW_ZOOM = 13" in appjs)
    check("stop marker source", "stop-markers" in appjs)
    check("numbered stop layers", "stop-label" in appjs and "stop-circle" in appjs)
    check("numbered site begin/end dots", "site-begin-label" in appjs and "site-end-label" in appjs)
    check("pick route map banner", "pick-banner" in idx and "pick_prompt" in appjs)
    check("pick letter labels", "siteDotLabel" in appjs and "pick_letters" in appjs)
    main_src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    check("pick route dropdown", "combo_pick_site" in main_src and "_on_pick_combo_chosen" in main_src)
    check("pick order dialog", "RoutePickOrderDialog" in main_src and "_show_route_pick_dialog" in main_src)
    from core.picocount import (
        build_unit_id, facing_n_or_e, preferred_counter_port, protocol_doc_present,
    )
    check("picocount unit id", build_unit_id(1234, "e") == "1234ec1b")
    check("picocount facing", facing_n_or_e("s") == "n" and facing_n_or_e("w") == "e")
    check("picocount protocol pdf", protocol_doc_present())
    check("picocount preferred port helper", callable(preferred_counter_port))
    check("picocount UI wired", "btn_counter_clear" in main_src and "PicocountThread" in main_src)
    check("counter status chip", "counterStatus" in main_src and "apply_counter_status" in main_src)
    from core import export
    check("export counter columns", "CounterUnitID" in export._EXPORT_COLS)
    from core import map_display
    check("map_display manual order", hasattr(map_display, "apply_manual_order"))
    check("segment path on map", "segment_path" in appjs)
    check("no drive leg trace", "tdSetDriveLeg = function ()" in appjs)
    check("no turn-by-turn banner", "navbar" not in idx)
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


def test_route_build_perf():
    print("[route build perf]")
    import road_router
    if not road_router.has_graph(DATA_DIR):
        print("  WARN skip — no road graph")
        return
    bench = os.path.join(ROOT, "scripts", "benchmark_route.py")
    py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    if not os.path.isfile(py):
        py = sys.executable
    import subprocess
    try:
        proc = subprocess.run(
            [py, bench], capture_output=True, text=True, timeout=300, cwd=ROOT)
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            for line in out.splitlines()[-8:]:
                print(f"    {line}")
        check("benchmark_route.py", proc.returncode == 0, out[-200:] if proc.returncode else "")
    except Exception as exc:
        check("benchmark_route.py", False, str(exc))


def test_routing():
    print("[routing]")
    import road_router
    for raw in road_router.OVERPASS_MIRRORS:
        interp = road_router.overpass_interpreter_url(raw)
        check("overpass mirror url", "/interpreter/interpreter" not in interp, interp)
    d = road_router.dist_to_polyline_m(33.77, -117.94, [[33.77, -117.94], [33.78, -117.95]])
    check("dist_to_polyline", 0 <= d < 5)
    g = road_router.load_graph(DATA_DIR) if road_router.graph_file_exists(DATA_DIR) else None
    if g is not None:
        start = (33.7715, -117.9431)
        dest = (33.85, -117.88)  # far enough for a real multi-node leg on the saved graph
        leg = road_router.leg_plan(g, start, dest, stop_index=0)
        check("leg_plan ok", leg.get("ok") and len(leg.get("maneuvers", [])) >= 2)
        plan = road_router.nav_plan(g, [start, dest])
        types = [m["type"] for m in plan.get("plan", [])]
        check("nav_plan has depart+arrive", "depart" in types and "arrive" in types)
        check("nav_plan legs", len(plan.get("legs", [])) == 1)
        ok(f"road graph ({len(g.nodes)} nodes)")
    elif road_router.graph_file_exists(DATA_DIR):
        detail = "osmnx missing — use .venv" if not road_router.HAS_ROUTING else "load failed"
        check("road graph load", False, detail)
    else:
        print("  WARN road_graph.graphml missing — download road map in Setup for full routing")


def test_field_ready():
    print("[field readiness]")
    from core.field_ready import check_all
    r = check_all(ROOT, probe_gps=False, stop_server_after=True)
    check("field_ready score", r["score"] >= 82, f"score={r['score']}")
    check("basemap ok", any(i["id"] == "basemap" and i["ok"] for i in r["items"]))
    check("map server ok", any(i["id"] == "server" and i["ok"] for i in r["items"]))
    check("picocount doc in readiness", any(i["id"] == "picocount_doc" for i in r["items"]))
    ok(f"readiness {r['score']}/100 ({r['warn_count']} warn, {r['fail_count']} fail)")


def test_golden_routes():
    print("[golden routes]")
    from scripts import golden_routes

    passed, msgs = golden_routes.verify()
    for m in msgs:
        mark = "OK" if "FAIL" not in m else "FAIL"
        print(f"  {mark}  {m}")
    check("golden route bands", passed, msgs[-1] if msgs else "")


def test_offline_session_script():
    print("[offline session]")
    import subprocess

    py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    if not os.path.isfile(py):
        py = sys.executable
    proc = subprocess.run(
        [py, os.path.join(ROOT, "scripts", "test_offline_session.py")],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=30,
    )
    check("test_offline_session.py", proc.returncode == 0, (proc.stdout or "") + (proc.stderr or ""))


def test_offline_no_internet():
    print("[offline field — no internet]")
    from core import geo, offline_policy
    offline_policy.set_field_mode(True)
    try:
        check("geocode blocked in field mode", geo.geocode_candidates("1 Main St, CA") == [])
        check("reverse geocode blocked", geo.street_from_coords(33.77, -117.94) == "")
        from core import connectivity
        check("connectivity probe skipped", connectivity.geocode_hosts_reachable() is None)
    finally:
        offline_policy.set_field_mode(False)


def test_voice_offline_gate():
    print("[voice / offline gate]")
    import voice_nav
    from core.offline_gate import evaluate as offline_gate_eval
    check("voice module", voice_nav.tts_available() or bool(voice_nav.tts_error()))
    r = {"items": [], "field_ready": True}
    g = offline_gate_eval(r, has_stops=True, route_miles=0, graph_loaded=True)
    check("offline gate blocks no route", not g["ok"] and g["blockers"])
    g2 = offline_gate_eval(r, has_stops=True, route_miles=12.5, graph_loaded=True)
    check("offline gate ok with route", g2["ok"])


def main() -> int:
    print(f"Traffic Deployer smoke_full — {ROOT}\n")
    test_imports()
    test_shift_summary()
    test_export_audit_counter()
    test_validate_merge()
    test_persistence()
    test_export()
    test_demo_data()
    test_web_assets()
    test_local_server()
    test_basemap()
    test_routing()
    test_route_build_perf()
    test_field_ready()
    test_golden_routes()
    test_offline_session_script()
    test_offline_no_internet()
    test_voice_offline_gate()
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
