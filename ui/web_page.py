"""Qt WebEngine page + vendor bootstrap for the map canvas."""
from __future__ import annotations

import os

from PySide6.QtCore import Signal, QFile, QIODevice
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
    """Intercept tdstop:// clicks from numbered map badges (QWebChannel is unreliable)."""
    stopClicked = Signal(str)

    def acceptNavigationRequest(self, url, nav_type, isMainFrame):
        if url.scheme() == "tdstop" and isMainFrame:
            uid = url.path().lstrip("/") or url.host()
            if uid:
                self.stopClicked.emit(uid)
            return False
        return super().acceptNavigationRequest(url, nav_type, isMainFrame)
