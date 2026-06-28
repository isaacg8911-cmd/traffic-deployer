"""Qt WebEngine page + vendor bootstrap for the map canvas."""
from __future__ import annotations

import os
from urllib.parse import unquote

from PySide6.QtCore import QUrlQuery, Signal, QFile, QIODevice
from PySide6.QtWebEngineCore import QWebEnginePage

from ui.paths import VENDOR_DIR


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
    """Intercept tdstop:// / tdmap:// from map (QWebChannel is unreliable)."""
    stopClicked = Signal(str)
    mapClicked = Signal(float, float)

    def acceptNavigationRequest(self, url, nav_type, isMainFrame):
        if isMainFrame and url.scheme() == "tdstop":
            raw = url.path().lstrip("/") or url.host()
            payload = unquote(raw) if raw else ""
            if payload:
                self.stopClicked.emit(payload)
            return False
        if isMainFrame and url.scheme() == "tdmap":
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
