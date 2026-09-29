"""Qt WebEngine page + vendor bootstrap for the map canvas."""
from __future__ import annotations

import os
from urllib.parse import unquote

from PySide6.QtCore import QUrl, QUrlQuery, Signal, QFile, QIODevice
from PySide6.QtWebEngineCore import QWebEnginePage

from ui.paths import VENDOR_DIR


def tdstop_payload(url: QUrl) -> str:
    """Site click payload from ``http://tdstop.local/pick?p=uid|begin``.

    Putting ``uid|side`` in a custom-scheme host (``tdstop://`` +
    encodeURIComponent) is an invalid URL, and WebEngine drops custom schemes
    before the page can see them. The query value is what actually arrives.
    """
    query = unquote(QUrlQuery(url.query()).queryItemValue("p") or "")
    if query:
        return query
    raw = unquote((url.path().lstrip("/") or url.host() or "").strip())
    return raw


def ensure_qwebchannel_js() -> None:
    dest = os.path.join(VENDOR_DIR, "qwebchannel.js")
    if os.path.exists(dest):
        return
    src = QFile(":/qtwebchannel/qwebchannel.js")
    if src.open(QIODevice.ReadOnly):
        data = bytes(src.readAll().data())
        src.close()
        with open(dest, "wb") as f:
            f.write(data)


class AppWebPage(QWebEnginePage):
    """Intercept map clicks when QWebChannel never connects.

    Custom schemes (tdstop://) are dropped by WebEngine before this hook.
    A normal http host that we cancel here still delivers the payload and
    does not leave the map page.
    """
    stopClicked = Signal(str)
    mapClicked = Signal(float, float)

    def acceptNavigationRequest(self, url, nav_type, isMainFrame):
        if not isMainFrame:
            return super().acceptNavigationRequest(url, nav_type, isMainFrame)
        host = (url.host() or "").lower()
        if url.scheme() == "tdstop" or host == "tdstop.local":
            payload = tdstop_payload(url)
            if payload:
                self.stopClicked.emit(payload)
            return False
        if url.scheme() == "tdmap" or host == "tdmap.local":
            lat_s = QUrlQuery(url.query()).queryItemValue("lat")
            lon_s = QUrlQuery(url.query()).queryItemValue("lon")
            if lat_s and lon_s:
                try:
                    self.mapClicked.emit(float(lat_s), float(lon_s))
                except ValueError:
                    pass
            else:
                raw = unquote((url.path().lstrip("/") or url.host() or "").strip())
                if raw and "," in raw:
                    parts = raw.split(",", 1)
                    try:
                        self.mapClicked.emit(float(parts[0]), float(parts[1]))
                    except ValueError:
                        pass
            return False
        return super().acceptNavigationRequest(url, nav_type, isMainFrame)
