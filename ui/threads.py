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


class GeocodeThread(QThread):
    """Forward geocode in background (network can take 5–20s)."""
    finished_result = Signal(list, str)

    def __init__(self, address: str, *, limit: int = 6):
        super().__init__()
        self.address = address.strip()
        self.limit = limit

    def run(self):
        if self.isInterruptionRequested():
            return
        from core import geo, offline_policy

        if not offline_policy.internet_features_allowed():
            self.finished_result.emit([], "offline")
            return
        if not geo.geocode_available():
            self.finished_result.emit([], "missing_requests")
            return
        try:
            cands = geo.geocode_candidates(self.address, limit=self.limit)
            if self.isInterruptionRequested():
                return
            self.finished_result.emit(cands, "")
        except Exception as exc:  # noqa: BLE001
            if not self.isInterruptionRequested():
                self.finished_result.emit([], str(exc))


class FieldStreetThread(QThread):
    """Reverse-geocode + road intel off the UI thread (pin/GPS save path)."""
    finished_result = Signal(int, float, float, str, str, str)

    def __init__(
        self,
        stop_idx: int,
        lat: float,
        lon: float,
        data_dir: str,
        *,
        prefer_online: bool = True,
    ):
        super().__init__()
        self.stop_idx = stop_idx
        self.lat = float(lat)
        self.lon = float(lon)
        self.data_dir = data_dir
        self.prefer_online = prefer_online

    def run(self):
        if self.isInterruptionRequested():
            return
        from core import geo

        street, src_tag = geo.street_for_field(
            self.lat, self.lon, self.data_dir, prefer_online=self.prefer_online)
        warning = ""
        if road_router.has_graph(self.data_dir):
            try:
                from core import street_intel

                g = road_router.load_graph(self.data_dir)
                if g is not None:
                    r = street_intel.analyze_point(g, self.lat, self.lon)
                    warning = str(r.get("message") or "").strip()
            except Exception:
                pass
        if not self.isInterruptionRequested():
            self.finished_result.emit(
                self.stop_idx, self.lat, self.lon, street or "", src_tag or "", warning)


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


class MapSetupThread(QThread):
    """Download California basemap + map assets (portable exe on Wi-Fi)."""
    finished_result = Signal(dict)

    def run(self):
        if self.isInterruptionRequested():
            return
        try:
            from core.map_setup import run_map_setup
            from ui.paths import APP_DIR, DATA_DIR, VENDOR_DIR, WEB_DIR

            run_map_setup(APP_DIR, WEB_DIR, DATA_DIR, VENDOR_DIR)
            if not self.isInterruptionRequested():
                self.finished_result.emit({"ok": True})
        except Exception as exc:  # noqa: BLE001
            if not self.isInterruptionRequested():
                self.finished_result.emit({"ok": False, "error": str(exc)})


class PicocountThread(QThread):
    """PicoCount 2500 serial ops off the UI thread (paced protocol)."""
    finished_result = Signal(dict)

    def __init__(self, operation: str, **kwargs):
        super().__init__()
        self.operation = operation
        self.kwargs = kwargs

    def run(self):
        if self.isInterruptionRequested():
            return
        from core import picocount
        op = self.operation
        port = self.kwargs.get("port")
        try:
            if op == "probe":
                self.finished_result.emit(picocount.read_counter_status(port))
            elif op == "serial":
                self.finished_result.emit(picocount.read_serial_number(port))
            elif op == "clear_configure":
                self.finished_result.emit(
                    picocount.clear_and_configure(
                        self.kwargs["unit_id"], port=port))
            elif op == "rename":
                self.finished_result.emit(
                    picocount.rename_unit_id(
                        self.kwargs["unit_id"], port=port))
            elif op == "memory":
                self.finished_result.emit(picocount.read_counter_status(port))
            elif op == "download":
                self.finished_result.emit(
                    picocount.download_study(
                        self.kwargs["dest_path"],
                        port=port,
                        meta=self.kwargs.get("meta"),
                    ))
            else:
                self.finished_result.emit(
                    {"ok": False, "error": f"Unknown picocount op: {op}"})
        except Exception as exc:  # noqa: BLE001
            if not self.isInterruptionRequested():
                self.finished_result.emit({"ok": False, "error": str(exc)})


class RouteApplyPickThread(QThread):
    """Apply manual pick order + trace route off the UI thread."""
    finished_result = Signal(dict)
    progress_text = Signal(str)

    def __init__(
        self,
        home: tuple,
        picked_uids: list[str],
        stops: list[dict],
        data_dir: str,
        pick_sides: dict[str, str] | None = None,
    ):
        super().__init__()
        self.home = home
        self.picked_uids = picked_uids
        self.stops = stops
        self.data_dir = data_dir
        self.pick_sides = dict(pick_sides or {})

    def run(self):
        import copy
        import traceback
        from core.map_display import apply_manual_order

        if self.isInterruptionRequested():
            return
        try:
            by_uid = {s["uid"]: s for s in self.stops}
            picked: list[dict] = []
            for uid in self.picked_uids:
                if uid not in by_uid:
                    continue
                stop = copy.deepcopy(by_uid[uid])
                side = self.pick_sides.get(uid)
                if side in ("begin", "end"):
                    stop["pick_cross_locked"] = True
                    stop["cross_side"] = side
                    if side == "begin":
                        stop["cross_lat"] = stop["begin_lat"]
                        stop["cross_lon"] = stop["begin_lon"]
                    else:
                        stop["cross_lat"] = stop["end_lat"]
                        stop["cross_lon"] = stop["end_lon"]
                picked.append(stop)
            if len(picked) != len(self.stops):
                self.finished_result.emit({
                    "ok": False,
                    "error": (
                        f"Pick all {len(self.stops)} stops on the map before Apply "
                        f"({len(picked)} chosen)."
                    ),
                })
                return
            self.progress_text.emit("Tracing route on real streets...")
            n = len(picked)
            self.progress_text.emit(
                f"Tracing route on map ({n} stops — about 5–20 sec)...")
            res = apply_manual_order(tuple(self.home), picked, self.data_dir)
            if self.isInterruptionRequested():
                return
            self.finished_result.emit({"ok": True, **res})
        except Exception as exc:  # noqa: BLE001
            if not self.isInterruptionRequested():
                self.finished_result.emit({
                    "ok": False,
                    "error": str(exc),
                    "trace": traceback.format_exc(),
                })


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
            trace_hi = max(12, min(45, n // 3 + 8))
            self.progress_text.emit(
                f"Drawing route on real streets ({n} stops — about 8–{trace_hi} sec)...")
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
