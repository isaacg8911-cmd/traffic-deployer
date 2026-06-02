"""Background QThreads for smoke, road download, and route optimization."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QThread, Signal

import road_router
from ui.paths import APP_DIR


class SmokeTestThread(QThread):
    finished_result = Signal(int, str)

    def run(self):
        import subprocess
        py = os.path.join(APP_DIR, ".venv", "Scripts", "python.exe")
        if not os.path.isfile(py):
            py = sys.executable
        script = os.path.join(APP_DIR, "scripts", "smoke_full.py")
        try:
            proc = subprocess.run(
                [py, script], capture_output=True, text=True, timeout=120, cwd=APP_DIR)
            out = (proc.stdout or "") + (proc.stderr or "")
            self.finished_result.emit(proc.returncode, out)
        except Exception as exc:
            self.finished_result.emit(1, str(exc))


class DownloadRoadsThread(QThread):
    """Download osmnx graph in a thread (network-bound; avoids flaky QProcess on Windows)."""
    finished_result = Signal(dict)

    def __init__(self, points: list, data_dir: str):
        super().__init__()
        self.points = points
        self.data_dir = data_dir

    def run(self):
        if self.isInterruptionRequested():
            return
        try:
            info = road_router.download_area(self.points, self.data_dir)
            if self.isInterruptionRequested():
                return
            self.finished_result.emit({"ok": True, **info})
        except Exception as exc:  # noqa: BLE001
            if not self.isInterruptionRequested():
                self.finished_result.emit({"ok": False, "error": str(exc)})


class RouteOptimizeThread(QThread):
    """Optimize + build route in a thread (same fix as download — no QProcess)."""
    finished_result = Signal(dict)
    progress_text = Signal(str)

    def __init__(self, stops: list, home: tuple, data_dir: str):
        super().__init__()
        self.stops = stops
        self.home = home
        self.data_dir = data_dir

    def run(self):
        import traceback
        from core import routing
        if self.isInterruptionRequested():
            return
        try:
            self.progress_text.emit(
                "Ordering stops (cross each street line — road network)...")
            res = routing.optimize(self.stops, self.home, self.data_dir)
            if self.isInterruptionRequested():
                return
            ordered = res["order"]
            n = len(ordered)
            self.progress_text.emit(
                f"Drawing route on real streets ({n} stops — about {max(15, n // 2)}–{max(30, n)} sec)...")
            route = routing.build_route(ordered, self.home, self.data_dir)
            if self.isInterruptionRequested():
                return
            self.finished_result.emit({
                "ok": True, "order": ordered, "route": route, "graph": res["graph"],
            })
        except Exception as exc:  # noqa: BLE001
            if not self.isInterruptionRequested():
                self.finished_result.emit({
                    "ok": False, "error": str(exc), "trace": traceback.format_exc(),
                })
