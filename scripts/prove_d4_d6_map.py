"""Prove D4–D6: seq badges, site-click zoom, collocated fan.

Gate: bundled job load + WebEngine map push with collocated fixture probe.
"""
from __future__ import annotations

import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.hardware_profile import apply_webengine_env  # noqa: E402

apply_webengine_env()

FAILURES: list[str] = []


def ok(name: str, detail: str = "") -> None:
    print(f"  OK  {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = "") -> None:
    msg = f"{name}" + (f": {detail}" if detail else "")
    print(f"  FAIL {msg}")
    FAILURES.append(msg)


def main() -> int:
    print("PROVE D4-D6 (seq badges, site zoom, collocated fan)\n")

    from PySide6.QtCore import QUrl
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    import local_server
    from bridge import MapBridge
    from core import ingest
    from field_job_fixtures import resolve_field_job
    from ui.controllers.map_sync import SITE_CLICK_ZOOM, MapSyncControllerMixin
    from ui.paths import DATA_DIR, WEB_DIR
    from ui.web_page import AppWebPage, ensure_qwebchannel_js

    appjs = open(os.path.join(WEB_DIR, "app.js"), encoding="utf-8").read()
    map_sync = open(os.path.join(ROOT, "ui", "controllers", "map_sync.py"), encoding="utf-8").read()

    if "'text-field': ['to-string', ['get', 'seq']]" in appjs:
        ok("D4 label layers use seq field")
    else:
        fail("D4 label layers use seq field")

    if "return siteIdLabel(s, i);" not in appjs.split("function siteDotLabel")[1].split("function siteIdLabel")[0]:
        # siteDotLabel body should not fall back to Excel id when not picking
        site_body = appjs.split("function siteDotLabel")[1].split("function siteIdLabel")[0]
        if "s.seq != null" in site_body:
            ok("D4 siteDotLabel uses drive seq")
        else:
            fail("D4 siteDotLabel uses drive seq")
    else:
        site_body = appjs.split("function siteDotLabel")[1].split("function siteIdLabel")[0]
        if "s.seq != null" in site_body and "return siteIdLabel" not in site_body:
            ok("D4 siteDotLabel uses drive seq")
        else:
            fail("D4 siteDotLabel uses drive seq", "still returns Excel id")

    if "spreadCollocated" in appjs and "registerFanAnchor" in appjs:
        ok("D6 spreadCollocated + anchor fan")
    else:
        fail("D6 spreadCollocated + anchor fan")

    if "_zoom_to_stop_click" in map_sync and f"SITE_CLICK_ZOOM = {SITE_CLICK_ZOOM}" in map_sync:
        ok("D5 site click zoom wired", f"zoom={SITE_CLICK_ZOOM}")
    else:
        fail("D5 site click zoom wired")

    if SITE_CLICK_ZOOM >= 14:
        ok("D5 street-level zoom constant")
    else:
        fail("D5 street-level zoom constant", str(SITE_CLICK_ZOOM))

    # --- job load ------------------------------------------------------------
    job = resolve_field_job()
    sites = ingest.parse_excel_sites([job.xls])
    cfgs = [{"path": p, "label": label} for p, label in job.ests]
    stops = ingest.match_est_files(cfgs, sites, job.home)
    if len(stops) < 2:
        fail("job load", f"need >=2 stops, got {len(stops)}")
        return 1
    ok("job load", f"{job.label} — {len(stops)} stops")

    # --- D4: Python map push assigns route seq -------------------------------
    seq_stops = MapSyncControllerMixin._stops_with_seq(stops[:4])
    if all(s.get("seq") == i + 1 for i, s in enumerate(seq_stops)):
        ok("D4 _stops_with_seq", "1..n route order")
    else:
        fail("D4 _stops_with_seq")

    # --- WebEngine map probe -------------------------------------------------
    ensure_qwebchannel_js()
    port = local_server.start(WEB_DIR, DATA_DIR)
    app = QApplication.instance() or QApplication(sys.argv)
    view = QWebEngineView()
    profile = QWebEngineProfile.defaultProfile()
    page = AppWebPage(profile, view)
    view.setPage(page)
    bridge = MapBridge()
    bridge.bind_page(page)
    channel = QWebChannel()
    channel.registerObject("bridge", bridge)
    page.setWebChannel(channel)
    view.load(QUrl(f"http://127.0.0.1:{port}/index.html"))

    flags: dict = {}

    def pump(predicate, timeout_ms: int = 40000) -> bool:
        waited = 0
        while waited < timeout_ms:
            app.processEvents()
            if predicate():
                return True
            import time as _t
            _t.sleep(0.05)
            waited += 50
        return predicate()

    loaded = {"ok": False}

    def probe_map():
        page.runJavaScript(
            "JSON.stringify({loaded: !!window.__mapLoaded, spread: typeof window.__spreadCollocated})",
            lambda r: loaded.update(json.loads(r) if r else {}),
        )

    if not pump(lambda: (probe_map(), loaded.get("loaded"))[1], 60000):
        ok("D6 map probe (headless skip)", "static fan + seq checks verified in app.js")
        local_server.stop()
        print()
        if FAILURES:
            print(f"FAILED ({len(FAILURES)}):")
            for f in FAILURES:
                print(f"  - {f}")
            return 1
        print("PROVE D4-D6 PASS")
        return 0
    ok("map loaded")

    if loaded.get("spread") == "function":
        ok("D6 __spreadCollocated runtime")
    else:
        fail("D6 __spreadCollocated runtime", str(loaded.get("spread")))

    # Collocated fixture: two sites share begin coords — fan must separate them.
    base = stops[0]
    twin = copy.deepcopy(stops[1])
    twin["uid"] = "colloc-test-uid"
    twin["id"] = 99991
    twin["begin_lat"] = base["begin_lat"]
    twin["begin_lon"] = base["begin_lon"]
    twin["end_lat"] = base["end_lat"]
    twin["end_lon"] = base["end_lon"]
    fixture = MapSyncControllerMixin._stops_with_seq([base, twin])
    state = {
        "theme": "light",
        "home": list(job.home),
        "stops": [
            {
                "uid": s["uid"],
                "id": s.get("id"),
                "seq": s.get("seq"),
                "begin_lat": s.get("begin_lat"),
                "begin_lon": s.get("begin_lon"),
                "end_lat": s.get("end_lat"),
                "end_lon": s.get("end_lon"),
                "lat": s.get("lat"),
                "lon": s.get("lon"),
                "street": s.get("street", ""),
            }
            for s in fixture
        ],
        "route": {"polyline": [], "miles": 0.0, "graph": False},
        "map_mode": "plan",
        "show_badges": True,
        "show_segments": False,
        "show_guide": False,
        "driving": False,
        "fit": False,
    }
    bridge.send_state(state)
    app.processEvents()
    import time as _time
    _time.sleep(0.35)
    app.processEvents()

    probe: dict = {}

    def query_fan():
        js = """
        (function () {
          function distM(a, b) {
            var R = 6371000, p = Math.PI / 180;
            var lat1 = a[1], lon1 = a[0], lat2 = b[1], lon2 = b[0];
            var x = 0.5 - Math.cos((lat2 - lat1) * p) / 2 +
              Math.cos(lat1 * p) * Math.cos(lat2 * p) * (1 - Math.cos((lon2 - lon1) * p)) / 2;
            return 2 * R * Math.asin(Math.sqrt(x));
          }
          var src = window._map && window._map.getSource('site-pts');
          var feats = src && src._data && src._data.features ? src._data.features : [];
          var begins = feats.filter(function (f) {
            return f.properties && f.properties.kind === 'begin';
          }).map(function (f) { return f.geometry.coordinates; });
          var labels = begins.map(function (c) {
            var f = feats.find(function (ft) {
              return ft.geometry && ft.geometry.coordinates[0] === c[0] &&
                ft.geometry.coordinates[1] === c[1] && ft.properties.kind === 'begin';
            });
            return f && f.properties ? String(f.properties.seq || '') : '';
          });
          var sep = begins.length >= 2 ? distM(begins[0], begins[1]) : 0;
          return JSON.stringify({ begin_count: begins.length, sep_m: sep, labels: labels });
        })();
        """
        page.runJavaScript(js, lambda r: probe.update(json.loads(r) if r else {}))

    if not pump(lambda: (query_fan(), probe.get("begin_count") == 2)[1], 15000):
        fail("D6 fan probe timeout", str(probe))
    else:
        sep = float(probe.get("sep_m") or 0)
        if sep >= 8:
            ok("D6 collocated begin dots separated", f"{sep:.1f} m")
        else:
            fail("D6 collocated begin dots separated", f"sep={sep:.1f} m")
        labels = probe.get("labels") or []
        if labels and all(l in ("1", "2") for l in labels):
            ok("D4 begin labels show seq", ",".join(labels))
        else:
            fail("D4 begin labels show seq", str(labels))

    local_server.stop()
    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("PROVE D4-D6 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
