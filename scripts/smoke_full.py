"""Headless smoke suite — run after every change: python scripts/smoke_full.py

GPS-focused subset: python scripts/smoke_full.py --gps-only
"""
from __future__ import annotations

import argparse
import json
import inspect
import os
import subprocess
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
    from version import APP_NAME, APP_VERSION
    check("core modules", True)
    check("version", APP_NAME == "Traffic Deployer" and APP_VERSION)
    ok(f"version {APP_VERSION}")
    from ui.map_helpers import (
        coords_moved,
        display_route_for_map,
        heading_cardinal,
        should_push_gps_bridge,
    )
    check("map_helpers dist still", coords_moved((0.0, 0.0), (0.0, 0.0), min_m=4.0) is False)
    check("map_helpers dist moved", coords_moved((0.0, 0.0), (0.0, 0.001), min_m=4.0) is True)
    check("map_helpers cardinal", heading_cardinal(0.0) == "N")
    check("map_helpers route", display_route_for_map({"miles": 1.2, "graph": True})["miles"] == 1.2)
    check(
        "map_helpers gps throttle",
        should_push_gps_bridge(
            33.0, -118.0, 90.0,
            last=None, last_t=0.0, now=1.0, heartbeat_s=5.0, min_m=4.0,
        ),
    )


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


def test_handoff():
    print("[handoff]")
    from core import export, handoff
    stops = [{
        "id": "7", "sheet": "Week 14 Day 1 Isaac", "street": "Main St", "serial": "ABC",
        "direction": "n", "lanes": 2, "installed": True, "field_lat": 33.77,
        "field_lon": -117.94, "skipped": False,
        "begin_lat": 33.771, "begin_lon": -117.941,
        "end_lat": 33.772, "end_lon": -117.942,
    }, {
        "id": "8", "sheet": "Week 14 Day 1 Isaac", "street": "Oak", "serial": "",
        "skipped": True, "installed": False,
        "begin_lat": 33.78, "begin_lon": -117.95,
        "end_lat": 33.781, "end_lon": -117.951,
    }]
    prefix = handoff.handoff_prefix(
        ig_tfc_path=r"c:\fake\week 14 ig tfc.xlsx",
        est_paths=[r"c:\fake\Week 14 Day 1 Isaac.est"],
    )
    check("handoff prefix", prefix == "Week 14")
    names = handoff.handoff_filenames(prefix, 2)
    check("handoff excel name", names["excel"] == "Week 14 IG TFC.xlsx")
    check("handoff map1 name", names["map1"] == "Week 14 Map 1.est")
    lat, lon = export._gps_pair(stops[0])
    check("gps installed only", lat == 33.77 and lon == -117.94)
    lat2, lon2 = export._gps_pair(stops[1])
    check("gps skipped empty", lat2 is None and lon2 is None)
    from core.est_viewer import sites_from_stops
    sites = sites_from_stops(stops)
    check("handoff map sites", len(sites) == 2)
    check("installed has field", sites[0].get("field_lat") == 33.77)
    check("skipped no field", "field_lat" not in sites[1])


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
    xlsx, xlsx_err = export.to_excel_result(stops, data_dir=DATA_DIR)
    check("excel export bytes", xlsx is not None and len(xlsx) > 500, xlsx_err or "")
    csv = export.to_csv_text(stops)
    check("csv export", "7" in csv and "-117.94" in csv)
    path = export.default_report_path(DATA_DIR, "SMOKE", "xlsx")
    check("export default path", path.endswith(".xlsx") and "IG_TFC_GPS" in path)
    check("export dir exists", os.path.isdir(export.export_dir(DATA_DIR)))


def test_maps_links():
    print("[maps links]")
    from core import maps_links
    stops = [
        {"id": "101", "street": "Main St", "cross_lat": 33.771, "cross_lon": -117.941},
        {"id": "102", "street": "Oak Ave", "lat": 33.78, "lon": -117.95},
    ]
    links, errs = maps_links.build_route_links(stops)
    check("route links count", len(links) == 2 and not errs)
    check("google maps url", "google.com/maps/dir" in links[0]["url"])
    check("uses cross coords", "33.771000" in links[0]["url"])
    txt = maps_links.to_plain_text(links, profile="WEEK9")
    check("plain text links", "Site 101" in txt and links[0]["url"] in txt)
    html_out = maps_links.to_html(links, profile="WEEK9", miles=12.5)
    check("html tap links", "<a href=" in html_out and "travelmode=driving" in html_out)
    path = maps_links.default_links_path(DATA_DIR, "SMOKE", kind="install")
    check("links default path", path.endswith(".html") and "exports" in path and "_Install" in path)
    pickup_stops = [
        {"uid": "a", "id": "1", "installed": True, "exact_time": "2026-06-10 14:00:00",
         "lat": 33.77, "lon": -117.94},
        {"uid": "b", "id": "2", "installed": True, "exact_time": "2026-06-10 09:00:00",
         "lat": 33.78, "lon": -117.95},
    ]
    ordered = maps_links.pickup_sequence_stops(pickup_stops)
    check("pickup install order", ordered[0]["id"] == "2" and ordered[1]["id"] == "1")
    shortcuts_src = open(
        os.path.join(ROOT, "ui", "controllers", "shortcuts.py"), encoding="utf-8"
    ).read()
    check(
        "phone nav wired",
        "_save_install_nav_links" in shortcuts_src and "_save_pickup_nav_links" in shortcuts_src,
    )
    from core import export
    row = {
        "Site": 15096, "Street": "DALTON SPRINGS LN", "ExactTime": "2026-06-17 07:58:09",
        "CrossLAT": 34.152524, "CrossLON": -117.838683, "LAT": 34.152208, "LON": -117.838765,
        "Installed": "x",
    }
    stop = export.stop_from_report_row(row, "Week 14 Day 2 Isaac")
    check("report row -> stop", stop and stop["installed"] and stop["id"] == "15096")
    ordered = maps_links.pickup_sequence_stops([
        stop,
        export.stop_from_report_row({
            **row, "Site": 15092, "ExactTime": "2026-06-17 08:11:43",
        }, "Week 14 Day 2 Isaac"),
    ])
    check("report pickup order", ordered and ordered[0]["id"] == "15096")


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
    check("local street labels to max zoom", "road-label-local" in style and "maxzoom: MAX_Z + 1" in style)
    check("lean labels optional", "text-optional': true" in style)
    check("no address clutter", "address-labels" not in style)
    check("follow street zoom", "FOLLOW_ZOOM = 13" in appjs)
    check("gps bridge throttle", "GPS_TICK_MS" in open(
        os.path.join(ROOT, "ui", "simple_mode.py"), encoding="utf-8").read())
    sm_src = open(os.path.join(ROOT, "ui", "simple_mode.py"), encoding="utf-8").read()
    check("battery saver timing", "BATTERY_GPS_TICK_MS" in sm_src and "timing_profile" in sm_src)
    check("work laptop timing", "WORK_LAPTOP_GPS_TICK_MS" in sm_src)
    from core import power as laptop_power
    from core import hardware_profile as hw
    from ui.simple_mode import timing_profile
    snap = laptop_power.read_power()
    check("power read", isinstance(snap.label, str))
    saver = timing_profile(on_ac=False, gps_follow=True)
    full = timing_profile(on_ac=True, gps_follow=True)
    wl = timing_profile(on_ac=True, gps_follow=True, work_laptop=True)
    check("battery slower gps", saver["gps_tick_ms"] > full["gps_tick_ms"])
    check("work laptop slower than full", wl["gps_tick_ms"] > full["gps_tick_ms"])
    check("work laptop faster than battery", wl["gps_tick_ms"] < saver["gps_tick_ms"])
    prof = hw.detect_hardware()
    check("hardware profile detect", isinstance(prof.work_laptop, bool))
    os.environ["TDS_WORK_LAPTOP"] = "1"
    check("hardware env flag", hw.detect_hardware().work_laptop)
    os.environ.pop("TDS_WORK_LAPTOP", None)
    check("lean gps render", "jumpTo" in appjs and "_gpsAnimId" not in appjs)
    check("lean drive path", "lean_drive" in appjs and "focusUid" in appjs)
    check("soft lean keeps roads", "LEAN_BASE_LAYERS" in appjs and "landuse" in appjs)
    check("follow zoom not locked", "zoom: map.getZoom()" in appjs)
    check("next site frame button", "next-site-btn" in idx and "__tdFrameNextSite" in appjs)
    check("stop marker source", "stop-markers" in appjs)
    check("numbered stop layers", "stop-label" in appjs and "stop-circle" in appjs)
    check("numbered site begin/end dots", "site-begin-label" in appjs and "site-end-label" in appjs)
    check("pick route map banner", "pick-banner" in idx and "pick_prompt" in appjs)
    check("pick letter labels", "siteDotLabel" in appjs and "pick_letters" in appjs)
    check("pick target dots", "pick-target-circle" in appjs and "pick-targets" in appjs)
    def _shell_src() -> str:
        chunks = [open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()]
        app_entry = os.path.join(ROOT, "ui", "app_entry.py")
        if os.path.isfile(app_entry):
            chunks.append(open(app_entry, encoding="utf-8").read())
        pages = os.path.join(ROOT, "ui", "pages")
        if os.path.isdir(pages):
            for name in sorted(os.listdir(pages)):
                if name.endswith(".py"):
                    chunks.append(open(os.path.join(pages, name), encoding="utf-8").read())
        controllers = os.path.join(ROOT, "ui", "controllers")
        if os.path.isdir(controllers):
            for name in sorted(os.listdir(controllers)):
                if name.endswith(".py"):
                    chunks.append(open(os.path.join(controllers, name), encoding="utf-8").read())
        shell = os.path.join(ROOT, "ui", "shell")
        if os.path.isdir(shell):
            for name in sorted(os.listdir(shell)):
                if name.endswith(".py"):
                    chunks.append(open(os.path.join(shell, name), encoding="utf-8").read())
        return "\n".join(chunks)

    main_src = _shell_src()
    check("power poll wired", "_poll_power" in main_src and "status_power" in main_src)
    check("work laptop wired", "_work_laptop" in main_src and "hardware_profile" in main_src)
    check("close stops workers", "closeEvent" in main_src and "_stop_worker(getattr" in main_src)
    check("gps timer starts", "gps_timer.start" in main_src)
    check("pick route dropdown", "combo_pick_site" in main_src and "_on_pick_combo_chosen" in main_src)
    check("pick map click nearest", "_nearest_unpicked_stop" in main_src and "_on_map_clicked" in main_src)
    check("pick order dialog", "RoutePickOrderDialog" in main_src and "_show_route_pick_dialog" in main_src)
    dlg_src = open(os.path.join(ROOT, "ui", "route_pick_dialog.py"), encoding="utf-8").read()
    check("pick dialog apply button", "apply_requested" in dlg_src and "btn_apply" in dlg_src)
    check("apply pick thread", "RouteApplyPickThread" in open(os.path.join(ROOT, "ui", "threads.py"), encoding="utf-8").read())
    import subprocess
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "test_ui_wiring.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    check("ui wiring audit", proc.returncode == 0, (proc.stdout or proc.stderr or "")[-400:])
    from core.picocount import (
        build_unit_id, counter_ports_labeled, facing_n_or_e, preferred_counter_port,
        protocol_doc_present,
    )
    check("picocount unit id", build_unit_id(1234, "e") == "1234ec1b")
    check("picocount facing", facing_n_or_e("s") == "n" and facing_n_or_e("w") == "e")
    from core import direction as direction_rules
    seg = direction_rules.infer_from_segment(33.0, -118.0, 33.001, -118.0)
    check("direction segment ns", seg["direction"] == "n" and seg["source"] == "segment")
    seg_ew = direction_rules.infer_from_segment(33.0, -118.0, 33.0, -117.99)
    check("direction segment ew", seg_ew["direction"] == "e")
    short = direction_rules.infer_from_segment(33.0, -118.0, 33.0, -118.0)
    check("direction short segment", short["direction"] is None and short["source"] == "needs_gps")
    from core.picocount import summarize_memory
    empty = summarize_memory({"page_size": 2048, "block_pages": 64, "block_ptr": 0, "page_ptr": 0, "buffer_ptr": 0})
    check("counter memory empty", empty.get("empty") and empty.get("bytes") == 0)
    check("picocount UI autoname", "btn_counter_autoname" in main_src and "_counter_autoname" in main_src)
    check("counter data label", "lbl_counter_data" in main_src and "_counter_show_memory" in main_src)
    check("counter connected pill", "counterConnectedPill" in main_src and "_set_counter_connected_ui" in main_src)
    check("install counter excel sync", "_sync_counter_fields" in main_src)
    from core.export import _row
    ex = _row({
        "installed": True, "id": "1234", "sheet": "Mon", "street": "Main St",
        "serial": "PC250012", "direction": "n", "lanes": 2,
        "counter_unit_id": "1234nc1b", "counter_serial": "PC250012",
        "date": "2026-06-09", "exact_time": "12:00",
    })
    check("export install serial", ex["Serial"] == "PC250012" and ex["CounterSerial"] == "PC250012")
    check("install checklist", "installChecklist" in main_src and "_refresh_install_checklist" in main_src)
    from core import install_checklist as ic
    items = ic.checklist_for_stop({
        "field_lat": 33.0, "field_lon": -118.0,
        "counter_cleared_at": "12:00", "serial": "PC99",
    })
    check("checklist all ready", ic.all_ready(items))
    dup = ic.find_duplicate_serial(
        [{"uid": "a", "serial": "PC99"}, {"uid": "b", "serial": "PC99"}],
        "a", "PC99",
    )
    check("duplicate serial detect", dup is not None and dup["uid"] == "b")
    check("no install photo ui", "Attach photo" not in main_src and "_attach_install_photo" not in main_src)
    from core import field_alerts as fa
    check("pickup reminder", fa.pending_download_count([
        {"installed": True, "counter_unit_id": "1234nc1b"},
    ]) == 1)
    check("shift closed", fa.shift_closed([{"installed": True}, {"skipped": True}]))
    from core import install_checklist as ic2
    check("install block reason", ic2.install_block_reason({}) is None)
    uid_dup = ic2.find_duplicate_unit_id(
        [{"uid": "a", "counter_unit_id": "1234nc1b"}, {"uid": "b", "counter_unit_id": "1234nc1b"}],
        "a", "1234nc1b",
    )
    check("duplicate unit id", uid_dup is not None and uid_dup["uid"] == "b")
    check("auto counter connect", "_counter_auto_connect" in main_src)
    check("export nudge", "_maybe_export_nudge" in main_src)
    check("pickup reminder ui", "lbl_pickup_reminder" in main_src)
    check("picocount protocol pdf", protocol_doc_present())
    check("picocount preferred port helper", callable(preferred_counter_port))
    check("picocount counter port filter", callable(counter_ports_labeled))
    check("field crash log hook", "install_crash_logging" in main_src)
    check("map guide when following", '"show_guide": bool(following)' in main_src)
    check("launch maximized", "showMaximized" in main_src)
    from core.picocount import is_gps_port, is_counter_port
    pc_src = open(os.path.join(ROOT, "core", "picocount.py"), encoding="utf-8").read()
    check("counter skips gps in probe", "_is_gps_port" in pc_src and "not _is_gps_port" in pc_src)
    check("counter port helpers", callable(is_gps_port) and callable(is_counter_port))
    check("picocount UI wired", "btn_counter_clear" in main_src and "PicocountThread" in main_src)
    check("counter refresh connect", "btn_counter_refresh" in main_src and "_counter_refresh_and_connect" in main_src)
    check("counter gps pause", "_counter_pause_gps" in main_src and "_counter_resume_gps" in main_src)
    check("counter status chip", "counterStatus" in main_src and "apply_counter_status" in main_src)
    from core import export
    check("export counter columns", "CounterUnitID" in export._EXPORT_COLS)
    from core import map_display
    check("map_display manual order", hasattr(map_display, "apply_manual_order"))
    check("segment path on map", "segment_path" in appjs)
    check("drive leg trace", "next_leg" in appjs and "build_site_legs" in open(os.path.join(ROOT, "core", "routing.py")).read())
    check("drive highlight", "__tdSetDriveHighlight" in appjs and "_next_leg_payload" in main_src)
    check("gps follow mode", "_gps_follow" in main_src and "btn_drive_arrived" in main_src)
    import main as main_mod
    grab_src = inspect.getsource(main_mod.MainWindow._grab_gps_here)
    commit_src = inspect.getsource(main_mod.MainWindow._commit_install)
    check("grab gps no blocking scan", "get_fix" not in grab_src and "fix_from_snapshot" in grab_src)
    check("manual grab map mode", "_manual_grab_mode" in main_src and "manual_grab" in appjs)
    check("manual grab save helper", "_save_field_position" in main_src)
    check("install persist on commit", "_persist_shift(quiet=True)" in commit_src and "saved locally" in commit_src)
    check("route on map plan", "_route_for_map(preview" in main_src)
    from ui.simple_mode import BUILD_LABEL, SIMPLE_MODE
    check("simple mode default", SIMPLE_MODE)
    check("simple build label", BUILD_LABEL == "BUILD ROUTE")
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
    from core import routing
    import road_router
    for raw in road_router.OVERPASS_MIRRORS:
        interp = road_router.overpass_interpreter_url(raw)
        check("overpass mirror url", "/interpreter/interpreter" not in interp, interp)
    d = road_router.dist_to_polyline_m(33.77, -117.94, [[33.77, -117.94], [33.78, -117.95]])
    check("dist_to_polyline", 0 <= d < 5)
    stops = [
        {"uid": "middle", "id": "M", "lat": 5.1, "lon": 0.0, "begin_lat": 5.0, "begin_lon": 0.0, "end_lat": 5.2, "end_lon": 0.0},
        {"uid": "home", "id": "H", "lat": 1.1, "lon": 0.0, "begin_lat": 1.0, "begin_lon": 0.0, "end_lat": 1.2, "end_lon": 0.0},
        {"uid": "far", "id": "F", "lat": 20.5, "lon": 0.0, "begin_lat": 20.0, "begin_lon": 0.0, "end_lat": 21.0, "end_lon": 0.0},
        {"uid": "near_far", "id": "NF", "lat": 19.85, "lon": 0.0, "begin_lat": 19.8, "begin_lon": 0.0, "end_lat": 19.9, "end_lon": 0.0},
    ]
    ordered = routing.optimize(stops, (0.0, 0.0), tempfile.mkdtemp())["order"]
    check("auto route starts furthest site", ordered[0]["id"] == "F")
    check("auto route chains nearby far site", ordered[1]["id"] == "NF")
    check("auto route ends nearest home", ordered[-1]["id"] == "H")
    check(
        "auto route uses closest final dot",
        ordered[-1]["cross_side"] == "begin"
        and abs(float(ordered[-1]["cross_lat"]) - 1.0) < 1e-9,
    )
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
        detail = "osmnx missing — use .venv" if not road_router.HAS_OSMNX else "load failed"
        check("road graph load", False, detail)
    else:
        print("  WARN road_graph.graphml missing — download road map in Setup for full routing")


def test_field_ready():
    print("[field readiness]")
    from core.field_ready import check_all
    r = check_all(ROOT, probe_gps=False, probe_counter=False, stop_server_after=True)
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


def test_offline_gate():
    print("[offline gate]")
    from core.offline_gate import evaluate as offline_gate_eval
    r = {"items": [], "field_ready": True}
    g = offline_gate_eval(r, has_stops=True, route_miles=0, graph_loaded=True)
    check("offline gate blocks no route", not g["ok"] and g["blockers"])
    g2 = offline_gate_eval(r, has_stops=True, route_miles=12.5, graph_loaded=True)
    check("offline gate ok with route", g2["ok"])
    check("no voice module", not os.path.isfile(os.path.join(ROOT, "voice_nav.py")))


def _shell_src() -> str:
    chunks = [open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()]
    app_entry = os.path.join(ROOT, "ui", "app_entry.py")
    if os.path.isfile(app_entry):
        chunks.append(open(app_entry, encoding="utf-8").read())
    pages = os.path.join(ROOT, "ui", "pages")
    if os.path.isdir(pages):
        for name in sorted(os.listdir(pages)):
            if name.endswith(".py"):
                chunks.append(open(os.path.join(pages, name), encoding="utf-8").read())
    controllers = os.path.join(ROOT, "ui", "controllers")
    if os.path.isdir(controllers):
        for name in sorted(os.listdir(controllers)):
            if name.endswith(".py"):
                chunks.append(open(os.path.join(controllers, name), encoding="utf-8").read())
    shell = os.path.join(ROOT, "ui", "shell")
    if os.path.isdir(shell):
        for name in sorted(os.listdir(shell)):
            if name.endswith(".py"):
                chunks.append(open(os.path.join(shell, name), encoding="utf-8").read())
    return "\n".join(chunks)


def _run_script(name: str, *, timeout: int = 60) -> tuple[int, str]:
    py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    if not os.path.isfile(py):
        py = sys.executable
    proc = subprocess.run(
        [py, os.path.join(ROOT, "scripts", name)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=timeout,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def test_gps_only():
    """GPS reader, grab-safe wiring, field coords, offline geocode — no routing/basemap."""
    print("[gps imports]")
    import gps_reader
    from gps_reader import GPSStream, fix_from_snapshot, no_fix_message
    import main as main_mod
    check("gps_reader import", True)
    check("GPSStream class", hasattr(gps_reader, "GPSStream"))

    print("[gps reader]")
    check("fix_from_snapshot none", fix_from_snapshot(None) is None)
    check("fix_from_snapshot no fix flag", fix_from_snapshot({"fix": False, "lat": 1.0, "lon": 2.0}) is None)
    pair = fix_from_snapshot({"fix": True, "lat": 33.7, "lon": -117.8})
    check("fix_from_snapshot ok", pair == (33.7, -117.8))
    check("no_fix_message disconnected", "No GPS found" in no_fix_message({"connected": False}))
    check("list_serial_ports", callable(gps_reader.list_serial_ports))
    st = gps_reader.get_status(attempts=2)
    check("get_status shape", isinstance(st, dict) and "connected" in st and "fix" in st)

    print("[grab gps safe]")
    rc, out = _run_script("test_grab_gps_safe.py")
    check("test_grab_gps_safe.py", rc == 0, out[-400:])

    print("[gps wiring]")
    appjs = open(os.path.join(WEB_DIR, "app.js"), encoding="utf-8").read()
    sm_src = open(os.path.join(ROOT, "ui", "simple_mode.py"), encoding="utf-8").read()
    main_src = _shell_src()
    check("gps bridge throttle", "GPS_TICK_MS" in sm_src)
    from ui.simple_mode import timing_profile
    saver = timing_profile(on_ac=False, gps_follow=True)
    full = timing_profile(on_ac=True, gps_follow=True)
    check("battery slower gps", saver["gps_tick_ms"] > full["gps_tick_ms"])
    check("lean gps render", "jumpTo" in appjs and "_gpsAnimId" not in appjs)
    check("gps timer starts", "gps_timer.start" in main_src)
    from ui.map_helpers import (
        coords_moved,
        display_route_for_map,
        heading_cardinal,
        should_push_gps_bridge,
    )
    check("map_helpers dist still", coords_moved((0.0, 0.0), (0.0, 0.0), min_m=4.0) is False)
    check("map_helpers dist moved", coords_moved((0.0, 0.0), (0.0, 0.001), min_m=4.0) is True)
    check("map_helpers cardinal", heading_cardinal(0.0) == "N")
    check("map_helpers route", display_route_for_map({"miles": 1.2, "graph": True})["miles"] == 1.2)
    check(
        "map_helpers gps throttle",
        should_push_gps_bridge(
            33.0, -118.0, 90.0,
            last=None, last_t=0.0, now=1.0, heartbeat_s=5.0, min_m=4.0,
        ),
    )
    from core import direction as direction_rules
    short = direction_rules.infer_from_segment(33.0, -118.0, 33.0, -118.0)
    check("direction needs gps", short["direction"] is None and short["source"] == "needs_gps")
    from core.picocount import is_gps_port, is_counter_port
    pc_src = open(os.path.join(ROOT, "core", "picocount.py"), encoding="utf-8").read()
    check("counter skips gps in probe", "_is_gps_port" in pc_src and "not _is_gps_port" in pc_src)
    check("counter port helpers", callable(is_gps_port) and callable(is_counter_port))
    check("counter gps pause", "_counter_pause_gps" in main_src and "_counter_resume_gps" in main_src)
    check("gps follow mode", "_gps_follow" in main_src and "btn_drive_arrived" in main_src)
    grab_src = inspect.getsource(main_mod.MainWindow._grab_gps_here)
    check("grab gps no blocking scan", "get_fix" not in grab_src and "fix_from_snapshot" in grab_src)
    check("manual grab map mode", "_manual_grab_mode" in main_src and "manual_grab" in appjs)
    check("manual grab save helper", "_save_field_position" in main_src)
    check("gps bridge in app.js", "pushGps" in appjs and "renderGps" in appjs)

    print("[field gps merge]")
    test_validate_merge()

    print("[est field gps]")
    from core.est_field_gps import detect_est_format, field_coords_from_stops
    inline = detect_est_format(b"\xff\xfe998\x14\x0825.12345\x15\t-118.12345")
    check("est inline format", inline == "inline")
    coords = field_coords_from_stops([{
        "id": "12", "installed": True, "field_lat": 33.77, "field_lon": -117.94,
    }])
    check("field coords from stops", coords == {"12": (33.77, -117.94)})

    print("[offline field — no internet]")
    test_offline_no_internet()


def test_volume_report():
    print("[volume report]")
    from core import volume_report

    pcbin = os.path.join(ROOT, "tds_data", "counter_downloads", "15126ec1b_live.pcbin")
    if not os.path.isfile(pcbin):
        ok("volume report (skip — no sample pcbin)")
        return
    res = volume_report.build_volume_report(
        pcbin,
        unit_id="15126ec1b",
        dir_primary="East",
        dir_secondary="West",
    )
    check("volume report parse", res.get("ok"), res.get("error", ""))
    if res.get("ok"):
        text = res.get("csv_text", "")
        check("volume header", text.startswith("Volume by Lane"))
        check("volume hourly rows", "Interval,,East,West" in text)
        check("volume grand total", "Grand Total" in text)
        check("volume vehicles", (res.get("vehicle_count") or 0) > 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Traffic Deployer headless smoke suite")
    ap.add_argument(
        "--gps-only",
        action="store_true",
        help="Run GPS reader / grab / field-coord checks only (fast, no routing/basemap)",
    )
    args = ap.parse_args(argv)

    label = "smoke_full (gps-only)" if args.gps_only else "smoke_full"
    print(f"Traffic Deployer {label} — {ROOT}\n")
    if args.gps_only:
        test_gps_only()
    else:
        test_imports()
        test_shift_summary()
        test_export_audit_counter()
        test_validate_merge()
        test_persistence()
        test_handoff()
        test_export()
        test_volume_report()
        test_maps_links()
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
        test_offline_gate()
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
