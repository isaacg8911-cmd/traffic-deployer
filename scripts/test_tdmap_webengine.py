"""Compare tdmap/tdstop delivery: direct handler vs WebEngine JS navigation vs bridge."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_direct_handler() -> None:
    from PySide6.QtCore import QUrl
    from ui.web_page import AppWebPage

    hits: list[tuple[float, float]] = []
    page = AppWebPage()
    page.mapClicked.connect(lambda la, lo: hits.append((la, lo)))
    page.acceptNavigationRequest(QUrl("tdmap://pin?lat=33.77&lon=-117.94"), 0, True)
    assert hits == [(33.77, -117.94)], hits


def test_js_navigation(scheme: str) -> list:
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from ui.web_page import AppWebPage

    app = QApplication.instance() or QApplication(sys.argv)
    hits: list = []

    page = AppWebPage()
    if scheme == "tdmap":
        page.mapClicked.connect(lambda la, lo: hits.append((la, lo)))
    else:
        page.stopClicked.connect(lambda s: hits.append(s))

    view = QWebEngineView()
    view.setPage(page)
    if scheme == "tdmap":
        nav = "window.location.href = 'tdmap://pin?lat=33.7715&lon=-117.9431';"
    else:
        nav = "window.location.href = 'tdstop://' + encodeURIComponent('abc123');"

    html = f"<!DOCTYPE html><html><body><script>setTimeout(function(){{{nav}}}, 100);</script></body></html>"
    done = {"ran": False}

    def finish_check() -> None:
        done["ran"] = True
        print(f"  JS {scheme} navigation hits={hits}")
        app.quit()

    view.loadFinished.connect(lambda ok: QTimer.singleShot(800, finish_check))
    view.setHtml(html, QUrl("http://127.0.0.1/"))
    app.exec()
    return hits


def test_bridge_map_click() -> list:
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from bridge import MapBridge
    from ui.web_page import AppWebPage

    app = QApplication.instance() or QApplication(sys.argv)
    hits: list[tuple[float, float]] = []

    page = AppWebPage()
    bridge = MapBridge()
    bridge.bind_page(page)
    bridge.mapClicked.connect(lambda la, lo: hits.append((la, lo)))
    channel = QWebChannel()
    channel.registerObject("bridge", bridge)
    page.setWebChannel(channel)

    view = QWebEngineView()
    view.setPage(page)

    html = """<!DOCTYPE html><html><body>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
new QWebChannel(qt.webChannelTransport, function(ch) {
  var bridge = ch.objects.bridge;
  setTimeout(function() { bridge.onMapClick(33.7715, -117.9431); }, 200);
});
</script></body></html>"""

    def finish_check() -> None:
        print(f"  bridge.onMapClick hits={hits}")
        app.quit()

    view.loadFinished.connect(lambda ok: QTimer.singleShot(1500, finish_check))
    view.setHtml(html, QUrl("http://127.0.0.1/"))
    app.exec()
    return hits


def main() -> int:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)
    fails = 0
    try:
        test_direct_handler()
        print("OK  direct acceptNavigationRequest")
    except Exception as exc:
        print(f"FAIL direct handler: {exc}")
        fails += 1

    # window.location.href tdmap/tdstop is NOT intercepted in Qt WebEngine (app.js uses bridge).
    for scheme in ("tdmap", "tdstop"):
        hits = test_js_navigation(scheme)
        if hits:
            print(f"OK  JS {scheme} navigation (unexpected hits={hits})")
        else:
            print(f"OK  JS {scheme} navigation (empty expected — production uses bridge.onMapClick)")

    hits = test_bridge_map_click()
    if hits and abs(hits[0][0] - 33.7715) < 1e-6:
        print("OK  bridge.onMapClick")
    else:
        print("FAIL bridge.onMapClick")
        fails += 1

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
