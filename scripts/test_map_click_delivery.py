"""Prove the JS->Python click path for map dots (the real WebEngine page).

The map RENDERS via Python->JS (runJavaScript), which works even if the
QWebChannel bridge never connects. But clicking an orange pick dot goes the
other way (JS->Python), through either:
  1. the QWebChannel `bridge.onStopClick(payload)` object, or
  2. the `http://tdstop.local/pick?p=` fallback -> AppWebPage.acceptNavigationRequest.

Custom schemes (`tdstop://uid|side`) are invalid URLs and WebEngine drops them,
so a down bridge used to lose every manual pick. This loads the actual served
page, enters pick mode with real stops, fires a real click, and asserts the
payload reached Python with the bridge connected and with it removed.
"""
from __future__ import annotations

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


def test_tdstop_query_url() -> None:
    """uid|side must survive as a query value. Host form is an invalid URL."""
    from urllib.parse import quote

    from PySide6.QtCore import QUrl

    from ui.web_page import tdstop_payload

    payload = "Day 1_101|begin"
    good = QUrl("tdstop://pick?p=" + quote(payload, safe=""))
    got = tdstop_payload(good)
    if good.isValid() and got == payload:
        ok("tdstop query keeps uid|side", got)
    else:
        fail("tdstop query keeps uid|side", f"valid={good.isValid()} got={got!r}")

    http = QUrl("http://tdstop.local/pick?p=" + quote(payload, safe=""))
    got_http = tdstop_payload(http)
    if http.isValid() and got_http == payload:
        ok("http click fallback keeps uid|side", got_http)
    else:
        fail("http click fallback keeps uid|side", f"valid={http.isValid()} got={got_http!r}")

    broken = QUrl("tdstop://" + quote(payload, safe=""))
    if broken.isValid() or tdstop_payload(broken):
        fail("old tdstop host form must not look usable", broken.errorString())
    else:
        ok("old tdstop host form is an invalid URL")


def main() -> int:
    print("MAP CLICK DELIVERY (JS -> Python)\n")
    test_tdstop_query_url()

    import json

    from PySide6.QtCore import QUrl, QTimer
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    import local_server
    from bridge import MapBridge
    from core import ingest
    from field_job_fixtures import resolve_field_job
    from ui.paths import DATA_DIR, WEB_DIR
    from ui.web_page import AppWebPage, ensure_qwebchannel_js

    job = resolve_field_job()
    sites = ingest.parse_excel_sites([job.xls])
    cfgs = [{"path": p, "label": label} for p, label in job.ests]
    stops = ingest.match_est_files(cfgs, sites, job.home)
    if len(stops) < 2:
        fail("need >=2 stops", str(len(stops)))
        return 1

    app = QApplication.instance() or QApplication(sys.argv)
    ensure_qwebchannel_js()
    port = local_server.start(WEB_DIR, DATA_DIR)

    received: list[str] = []
    map_received: list[tuple[float, float]] = []

    view = QWebEngineView()
    profile = QWebEngineProfile.defaultProfile()
    # Default profile caches app.js across runs; a stale file hides fallback fixes.
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
    page = AppWebPage(profile, view)
    page.stopClicked.connect(lambda p: received.append(("scheme", p)))
    page.mapClicked.connect(lambda a, b: map_received.append((a, b)))
    view.setPage(page)

    bridge = MapBridge()
    bridge.bind_page(page)
    bridge.stopClicked.connect(lambda p: received.append(("bridge", p)))
    bridge.mapClicked.connect(lambda a, b: map_received.append((a, b)))
    channel = QWebChannel()
    channel.registerObject("bridge", bridge)
    page.setWebChannel(channel)

    view.load(QUrl(f"http://127.0.0.1:{port}/index.html"))

    def pump(predicate, timeout_ms: int, tick_ms: int = 50) -> bool:
        waited = 0
        while waited < timeout_ms:
            app.processEvents()
            if predicate():
                return True
            QTimer.singleShot(tick_ms, lambda: None)
            import time as _t
            _t.sleep(tick_ms / 1000.0)
            waited += tick_ms
        return app.processEvents() or predicate()

    # --- wait for map + bridge ------------------------------------------------
    flags: dict[str, object] = {}

    def probe():
        page.runJavaScript(
            "JSON.stringify({loaded: !!window.__mapLoaded, "
            "bridge: !!window.__bridgeReady, errs: (window.__jsErrors||[])})",
            lambda r: flags.update(json.loads(r) if r else {}),
        )

    # The bridge (JS->Python) is what the click path needs; the offscreen map may
    # never fire 'load' without a GL surface, so don't gate on window.__mapLoaded.
    def bridge_ready():
        probe()
        return bool(flags.get("bridge"))

    if not pump(bridge_ready, 40000):
        fail("QWebChannel bridge connect", f"flags={flags}")
    else:
        ok("QWebChannel bridge connected", "window.__bridgeReady true")
    if flags.get("loaded"):
        ok("map loaded", "window.__mapLoaded")

    # --- push a pick-mode state with real stops -------------------------------
    def stop_payload(s: dict) -> dict:
        return {
            "uid": str(s["uid"]),
            "id": s.get("id"),
            "begin_lat": s.get("begin_lat"),
            "begin_lon": s.get("begin_lon"),
            "end_lat": s.get("end_lat"),
            "end_lon": s.get("end_lon"),
            "lat": s.get("lat"),
            "lon": s.get("lon"),
        }

    state = {
        "theme": "light",
        "home": list(job.home),
        "stops": [stop_payload(s) for s in stops],
        "map_mode": "pick",
        "pick_order": [],
        "pick_letters": {str(s["uid"]): chr(65 + i) for i, s in enumerate(stops)},
        "show_badges": False,
        "fit": True,
    }
    bridge.send_state(state)
    pump(lambda: False, 500)

    uid0 = str(stops[0]["uid"])
    payload0 = f"{uid0}|begin"

    # Confirm bridge init did not throw (the pushState/.connect mismatch bug).
    errs = flags.get("errs") or []
    if any("connect" in str(e) for e in errs):
        fail("bridge init threw", str(errs))
    else:
        ok("bridge init clean (no signal-connect throw)")

    # --- fire the exact JS->Python click path a dot uses (fireStopClick) -------
    received.clear()
    map_received.clear()
    page.runJavaScript(f"window.__fireStopClick({json.dumps(payload0)})", lambda _r: None)
    pump(lambda: len(received) > 0 or len(map_received) > 0, 4000)

    if received:
        via, payload = received[-1]
        if str(payload).split("|", 1)[0] == uid0:
            ok("dot click reached Python", f"via {via}: {payload}")
        else:
            fail("dot click wrong uid", f"via {via}: {payload}")
    else:
        fail("dot click NEVER reached Python",
             "this is the field 'dots dead' bug")

    # --- verify the tdstop:// scheme fallback when bridge is unavailable -------
    # `bridge` lives inside the page IIFE. A page-global `bridge = null` does
    # not disconnect fireStopClick — that used to make this test a false pass.
    received.clear()
    map_received.clear()
    page.runJavaScript("window.__dropBridge()", lambda _r: None)
    pump(lambda: False, 200)
    page.runJavaScript(f"window.__fireStopClick({json.dumps(payload0)})", lambda _r: None)
    pump(lambda: len(received) > 0 or len(map_received) > 0, 4000)
    if received and received[-1][0] == "scheme" and str(received[-1][1]) == payload0:
        ok("scheme fallback reached Python", f"{received[-1][1]}")
    else:
        fail("tdstop:// scheme fallback DEAD",
             f"got {received or map_received!r} — clicks lost when QWebChannel is down")

    received.clear()
    map_received.clear()
    page.runJavaScript("window.__fireMapClick(34.15, -117.84)", lambda _r: None)
    pump(lambda: len(map_received) > 0, 4000)
    if map_received and abs(map_received[-1][0] - 34.15) < 1e-6:
        ok("map-click fallback reached Python", str(map_received[-1]))
    else:
        fail("map-click fallback DEAD", str(map_received))

    local_server.stop()
    print("\n" + "=" * 50)
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
        print("MAP CLICK DELIVERY FAIL")
        return 1
    print("MAP CLICK DELIVERY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
