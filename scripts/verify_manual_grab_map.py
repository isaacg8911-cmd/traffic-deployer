"""Verify manual grab map click URL + wiring (Qt parses tdmap query correctly)."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

APP_JS = os.path.join(ROOT, "web", "app.js")
MAIN_PY = os.path.join(ROOT, "main.py")
STARTUP_PY = os.path.join(ROOT, "ui", "shell", "startup.py")
INSTALL_CONTROLLER_PY = os.path.join(ROOT, "ui", "controllers", "install.py")
BRIDGE_PY = os.path.join(ROOT, "bridge.py")


def test_tdmap_url_parsing() -> None:
    from PySide6.QtCore import QUrl, QUrlQuery

    lat, lon = 33.7715, -117.9431
    url = QUrl(f"tdmap://pin?lat={lat}&lon={lon}")
    q = QUrlQuery(url.query())
    got_lat = float(q.queryItemValue("lat"))
    got_lon = float(q.queryItemValue("lon"))
    assert got_lat == lat and got_lon == lon, (got_lat, got_lon)

    from urllib.parse import quote

    broken = QUrl("tdmap://" + quote(f"{lat},{lon}", safe=""))
    raw = (broken.path().lstrip("/") or broken.host() or "").strip()
    assert not raw, "encoded comma tdmap URL must stay broken (documents old bug)"


def test_web_page_handler() -> None:
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import QApplication
    from ui.web_page import AppWebPage

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    hits: list[tuple[float, float]] = []

    class Page(AppWebPage):
        def __init__(self):
            super().__init__()
            self.mapClicked.connect(lambda la, lo: hits.append((la, lo)))

    page = Page()
    ok = page.acceptNavigationRequest(
        QUrl("tdmap://pin?lat=33.77&lon=-117.94"), 0, True)
    assert ok is False
    assert hits == [(33.77, -117.94)]


def test_fire_map_click_uses_bridge_first() -> None:
    appjs = open(APP_JS, encoding="utf-8").read()
    start = appjs.index("function fireMapClick")
    body = appjs[start:start + 600]
    bridge_idx = body.find("bridge.onMapClick")
    tdmap_idx = body.find("window.location.href = tdmapUrl")
    assert bridge_idx >= 0 and tdmap_idx >= 0, "fireMapClick must use bridge and tdmap fallback"
    assert bridge_idx < tdmap_idx, "fireMapClick must call bridge before tdmap fallback"
    assert "forceTdmap" not in body, "manual grab must not bypass bridge with forceTdmap"


def test_manual_grab_click_saves_immediately() -> None:
    appjs = open(APP_JS, encoding="utf-8").read()
    assert "manualGrabPinAt(e.lngLat.lat, e.lngLat.lng)" in appjs
    assert "function manualGrabPinAt" in appjs
    grab_fn = appjs.split("function manualGrabPinAt", 1)[1].split("window.__tdSetManualGrab", 1)[0]
    assert "fireMapClick(lat, lon)" in grab_fn, "manual grab must save GPS on map click"
    assert "function confirmDropPin" in appjs
    assert "setFollow(false)" in appjs.split("window.__tdSetManualGrab", 1)[1][:400]


def test_source_wiring() -> None:
    appjs = open(APP_JS, encoding="utf-8").read()
    main = open(MAIN_PY, encoding="utf-8").read()
    startup = open(STARTUP_PY, encoding="utf-8").read()
    install_controller = open(INSTALL_CONTROLLER_PY, encoding="utf-8").read()
    bridge = open(BRIDGE_PY, encoding="utf-8").read()
    checks = {
        "tdmap://pin?lat=": appjs,
        "__tdSetManualGrab": appjs,
        "__tdConfirmDropPin": appjs,
        "__tdPatchFieldPin": appjs,
        "fieldCoordsOk": appjs,
        "__tdSimManualGrabClick": appjs,
        "__tdLastPinDrop": appjs,
        "showDropPin": appjs,
        "page.mapClicked.connect": startup,
        "set_manual_grab": bridge,
        "_confirm_manual_grab_pin": install_controller,
    }
    for needle, blob in checks.items():
        assert needle in blob, needle


def main() -> int:
    fails = 0
    for name, fn in (
        ("tdmap QUrl query parse", test_tdmap_url_parsing),
        ("AppWebPage tdmap handler", test_web_page_handler),
        ("fireMapClick bridge-first", test_fire_map_click_uses_bridge_first),
        ("manual grab click saves", test_manual_grab_click_saves_immediately),
        ("source wiring", test_source_wiring),
    ):
        try:
            fn()
            print(f"OK  {name}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {name}: {exc}")
            fails += 1
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
