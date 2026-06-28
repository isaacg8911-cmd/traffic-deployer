"""Prove offline field map keeps basemap + pins (no Wi‑Fi required).

Checks:
  1. lean_drive only when offline + GPS follow + work laptop
  2. app.js never blanks the map on offline Route view
  3. localhost serves california.pmtiles (offline basemap)
  4. WebEngine: push offline state -> stop markers + road layers visible

    python scripts/test_offline_map.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

WEB = os.path.join(ROOT, "web")
DATA = os.path.join(ROOT, "tds_data")
APP_JS = os.path.join(WEB, "app.js")


def lean_drive(*, offline_mode: bool, following: bool, work_laptop: bool) -> bool:
    return bool(offline_mode) and following and work_laptop


def sample_stop(uid: str = "s1", seq: int = 1) -> dict:
    return {
        "uid": uid,
        "id": str(1000 + seq),
        "seq": seq,
        "lat": 33.7715,
        "lon": -117.9431,
        "cross_lat": 33.7716,
        "cross_lon": -117.9430,
        "begin_lat": 33.7714,
        "begin_lon": -117.9435,
        "end_lat": 33.7718,
        "end_lon": -117.9426,
        "street": "Main St",
        "installed": False,
        "skipped": False,
    }


def base_state(**overrides) -> dict:
    st = {
        "theme": "sunny",
        "home": [33.7700, -117.9450],
        "stops": [sample_stop("s1", 1), sample_stop("s2", 2)],
        "route": {"polyline": [], "miles": 4.2, "graph": True},
        "next_leg": None,
        "fit": False,
        "driving": False,
        "map_mode": "plan",
        "highlight_uid": "s1",
        "drive_target_uid": "s1",
        "pick_order": [],
        "pick_prompt": "",
        "pick_waiting": "",
        "pick_letters": {},
        "show_segments": True,
        "show_badges": True,
        "show_guide": False,
        "lean_drive": False,
    }
    st.update(overrides)
    return st


def test_lean_drive_matrix() -> None:
    assert not lean_drive(offline_mode=True, following=False, work_laptop=True), (
        "Go offline on Route must NOT enable lean_drive"
    )
    assert not lean_drive(offline_mode=True, following=False, work_laptop=False)
    assert lean_drive(offline_mode=True, following=True, work_laptop=True), (
        "GPS follow on work laptop may use soft lean only"
    )
    assert not lean_drive(offline_mode=True, following=True, work_laptop=False)
    assert not lean_drive(offline_mode=False, following=True, work_laptop=True)


def test_appjs_no_blank_offline_path() -> None:
    src = open(APP_JS, encoding="utf-8").read()
    assert "applyLeanDriveData" not in src, "blank-map lean path must be removed"
    assert "setBasemapLabels(true)" in src, "street labels must stay on offline"
    assert "'landuse'" in src.split("LEAN_BASE_LAYERS", 1)[1][:80], (
        "soft lean should only drop landuse tint"
    )
    assert "roads-all" not in src.split("LEAN_BASE_LAYERS", 1)[1][:120], (
        "roads must not be in LEAN_BASE_LAYERS"
    )
    lean_block = src.split("var focusUid", 1)[1][:200]
    assert "lean && driving" in lean_block, "focus filter only during lean GPS follow"


def test_local_basemap_no_internet() -> None:
    import local_server

    local_server.stop()
    port = local_server.start(WEB, DATA)
    base = f"http://127.0.0.1:{port}"
    idx = urllib.request.urlopen(base + "/", timeout=5).read()
    assert b"app.js" in idx or b"map" in idx.lower(), "index.html must reference map app"
    pmt = os.path.join(DATA, "california.pmtiles")
    assert os.path.isfile(pmt), f"missing offline basemap: {pmt}"
    head = urllib.request.urlopen(base + "/data/california.pmtiles", timeout=10)
    assert head.status == 200
    assert int(head.headers.get("Content-Length", "0")) > 1_000_000
    assert head.headers.get("Accept-Ranges") == "bytes", "PMTiles needs Range support"
    local_server.stop()


def _run_webengine_probe(state: dict, *, label: str) -> dict:
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView

    import local_server

    local_server.stop()
    port = local_server.start(WEB, DATA)
    app = QApplication.instance() or QApplication(sys.argv)
    view = QWebEngineView()
    view.resize(1024, 768)
    view.show()
    result: dict = {"label": label, "err": "timeout"}

    probe_js = """
    (function () {
      if (!window.__mapLoaded || !window._map) {
        return JSON.stringify({ ok: false, err: 'map_not_loaded', dbg: window.__dbg || {} });
      }
      var m = window._map;
      var sm = m.getSource('stop-markers');
      var nStops = (sm && sm._data && sm._data.features) ? sm._data.features.length : -1;
      function vis(id) {
        if (!m.getLayer(id)) return 'missing';
        return m.getLayoutProperty(id, 'visibility') || 'visible';
      }
      return JSON.stringify({
        ok: true,
        stops: nStops,
        roads: vis('roads-all'),
        labels: vis('road-label-local'),
        dbg: window.__dbg || {}
      });
    })()
    """

    def finish(raw: str | None) -> None:
        nonlocal result
        try:
            result = json.loads(raw or "{}")
        except json.JSONDecodeError:
            result = {"ok": False, "err": f"bad_json:{raw!r}"}
        result["label"] = label
        app.quit()

    def after_push(_raw: str | None) -> None:
        QTimer.singleShot(1500, lambda: view.page().runJavaScript(probe_js, finish))

    def on_loaded(ok: bool) -> None:
        if not ok:
            finish(json.dumps({"ok": False, "err": "load_failed"}))
            return
        payload = json.dumps(state)
        view.page().runJavaScript(
            f"window.__tdPushState && window.__tdPushState({payload}); 'pushed';",
            lambda _: QTimer.singleShot(500, lambda: after_push(None)),
        )

    view.loadFinished.connect(on_loaded)
    view.load(QUrl(f"http://127.0.0.1:{port}/"))
    QTimer.singleShot(45_000, lambda: finish(json.dumps({"ok": False, "err": "timeout"})))
    app.exec()
    local_server.stop()
    return result


def test_webengine_offline_route_map() -> None:
    st = base_state(
        lean_drive=False,
        driving=False,
        map_mode="plan",
        show_guide=False,
    )
    r = _run_webengine_probe(st, label="offline_route")
    assert r.get("ok"), r
    assert r.get("stops", 0) >= 2, f"expected stop markers, got {r}"
    assert r.get("roads") in ("visible", None), f"roads hidden: {r}"
    assert r.get("labels") in ("visible", None), f"street labels hidden: {r}"


def test_webengine_soft_lean_follow() -> None:
    st = base_state(
        lean_drive=True,
        driving=True,
        map_mode="drive",
        show_guide=True,
        next_leg={"polyline": [[33.77, -117.95], [33.7716, -117.9430]], "miles": 0.3},
        highlight_uid="s1",
        drive_target_uid="s1",
        stops=[sample_stop("s1", 1), sample_stop("s2", 2)],
    )
    r = _run_webengine_probe(st, label="soft_lean_follow")
    assert r.get("ok"), r
    assert r.get("roads") in ("visible", None), f"soft lean must keep roads: {r}"
    assert r.get("labels") in ("visible", None), f"soft lean must keep labels: {r}"
    assert r.get("stops", 0) == 1, f"soft lean shows next stop only, got {r}"


def main() -> int:
    fails = 0
    tests = [
        ("lean_drive matrix", test_lean_drive_matrix),
        ("app.js offline map contract", test_appjs_no_blank_offline_path),
        ("local basemap (no internet)", test_local_basemap_no_internet),
        ("WebEngine offline Route map", test_webengine_offline_route_map),
        ("WebEngine soft lean follow", test_webengine_soft_lean_follow),
    ]
    for name, fn in tests:
        try:
            fn()
            print(f"OK  {name}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {name}: {exc}")
            fails += 1
    if fails:
        print(f"\n{ fails } failed")
        return 1
    print("\nOK: offline map checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
