"""Bridge between Python and the MapLibre map canvas.

Python -> JS uses QWebEnginePage.runJavaScript (reliable over localhost).
QWebChannel is kept only for optional JS -> Python callbacks (stop clicks).
"""
from __future__ import annotations

import json
import math

from PySide6.QtCore import QObject, Signal, Slot


def _clean(obj):
    """Replace NaN/Infinity with None so JSON is parseable in the browser."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


def _dumps(obj) -> str:
    return json.dumps(_clean(obj), allow_nan=False, default=str)


class MapBridge(QObject):
    mapReady = Signal()
    mapClicked = Signal(float, float)
    stopClicked = Signal(str)
    followToggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page = None

    def bind_page(self, page):
        self._page = page

    def _run(self, js: str):
        if self._page is not None:
            self._page.runJavaScript(js)

    @Slot()
    def onReady(self):
        self.mapReady.emit()

    @Slot(float, float)
    def onMapClick(self, lat: float, lon: float):
        self.mapClicked.emit(lat, lon)

    @Slot(str)
    def onStopClick(self, uid: str):
        self.stopClicked.emit(uid)

    @Slot(bool)
    def onFollowToggled(self, on: bool):
        self.followToggled.emit(bool(on))

    def send_state(self, state: dict):
        self._run(f"window.__tdPushState && window.__tdPushState({_dumps(state)})")

    def send_gps(self, gps: dict):
        self._run(f"window.__tdPushGps && window.__tdPushGps({_dumps(gps)})")

    def send_nav(self, nav: dict):
        self._run(f"window.__tdPushNav && window.__tdPushNav({_dumps(nav)})")

    def fly_to(self, lat: float, lon: float, zoom: int = 13):
        self._run(f"window.__tdFlyTo && window.__tdFlyTo({float(lat)}, {float(lon)}, {int(zoom)})")

    def set_follow(self, on: bool):
        self._run(f"window.__tdSetFollow && window.__tdSetFollow({'true' if on else 'false'})")

    def refresh_view(self):
        self._run("window.__tdRefresh && window.__tdRefresh()")

    def send_drive_leg(self, polyline: list, *, active: bool = True):
        """Update only the tron route line (fast path while driving)."""
        self._run(
            f"window.__tdSetDriveLeg && window.__tdSetDriveLeg({_dumps(polyline)}, {str(active).lower()})"
        )

    def set_manual_grab(self, on: bool, prompt: str = "") -> None:
        """Manual pin mode is driven by push_state; this is a safe no-op hook."""
        _ = (on, prompt)

    def send_field_pin(
        self,
        uid: str,
        lat: float,
        lon: float,
        site_id: str,
        *,
        pending: bool = False,
        source: str = "gps",
        draggable: bool = False,
    ) -> None:
        """Place the install field pin immediately — distinct from the live GPS dot."""
        _ = (uid, site_id, pending)
        src = _dumps(str(source or "gps"))
        drag = "true" if draggable else "false"
        self._run(
            f"window.__tdSetFieldPin && window.__tdSetFieldPin("
            f"{float(lat)}, {float(lon)}, {src}, {drag})"
        )

    def clear_field_pin(self) -> None:
        self._run("window.__tdClearFieldPin && window.__tdClearFieldPin()")
