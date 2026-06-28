"""MainWindow startup wiring — P46 extract from main.py."""

from __future__ import annotations

import os

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMessageBox

import gps_reader
import local_server
from bridge import MapBridge
from core.hardware_profile import default_window_size, is_work_laptop, web_http_cache_bytes
from core.state import RouteState
from ui.paths import DATA_DIR, WEB_DIR, web_assets_ok
from ui.route_pick_dialog import RoutePickOrderDialog
from ui.simple_mode import GPS_PUSH_HEARTBEAT_S, GPS_PUSH_MIN_M
from ui.web_page import AppWebPage, ensure_qwebchannel_js
from ui_themes import normalize_theme, qt_stylesheet
from version import APP_NAME, APP_VERSION


class ShellStartupMixin:
    def _init_window_startup(self) -> None:
        self._init_state_and_flags()
        self._init_persistence_timers()
        self._init_map_view()
        self._init_shell_ui()
        self._init_gps_and_deferred_refresh()

    def _init_state_and_flags(self) -> None:
        self._work_laptop = is_work_laptop()
        w, h = default_window_size()
        self.resize(w, h)
        self.state = RouteState(DATA_DIR, profile="DEFAULT")
        self.state.load()
        self._sync_field_mode()
        self.state.theme = normalize_theme(self.state.theme)
        self.setStyleSheet(qt_stylesheet(self.state.theme))
        if self.state.default_home:
            self.state.apply_default_home()
        elif self.state.saved_home_coords:
            self.state.home = self.state.saved_home_coords
        self.current_index = min(self.state.current_index, max(0, len(self.state.stops) - 1))
        self.pickup_index = self.state.pickup_index
        self.excel_paths = [p for p in self.state.excel_paths if os.path.isfile(p)]
        self._route_pick_mode = False
        self._route_pick_uids: list[str] = []
        self._route_pick_sides: dict[str, str] = {}
        self._route_pick_dialog: RoutePickOrderDialog | None = None
        self._manual_grab_mode = False
        self._follow_before_manual_grab = False
        self._picocount_thread = None
        self._counter_serial_grab_uid: str | None = None
        self._counter_connected = False
        self._counter_memory_bytes: int | None = None
        self._export_nudge_shown = False
        self._gps_paused_for_counter = False
        self.est_paths = [p for p in self.state.est_paths if os.path.isfile(p)]
        self.state.excel_paths = list(self.excel_paths)
        self.state.est_paths = list(self.est_paths)
        self._map_preview_stops: list[dict] = []
        self._map_preview_route: dict = {"polyline": [], "miles": 0.0, "graph": False}
        self.nav: dict = {"active": False}  # legacy alias; use _gps_follow
        self._gps_follow = False
        self._nav_thread = None
        self._undo_stack: list[dict] = []
        self._last_leg_push = 0.0
        self._splitter_sizes_saved: list[int] | None = None
        self._pick_splitter_saved: list[int] | None = None
        self._pick_layout_active = False
        self._strip_tick = 0.0
        self._last_gps_bridge: tuple[float, float, float | None] | None = None
        self._last_gps_bridge_t = 0.0
        self._power_on_ac: bool | None = None
        self._power_label = ""
        self._gps_push_min_m = GPS_PUSH_MIN_M
        self._gps_push_heartbeat_s = GPS_PUSH_HEARTBEAT_S
        self._strip_throttle_s = 2.0
        self._route_thread = None
        self._dl_thread = None
        self._geocode_thread = None
        self._field_street_thread = None

    def _init_persistence_timers(self) -> None:
        self._pin_persist_timer = QTimer(self)
        self._pin_persist_timer.setSingleShot(True)
        self._pin_persist_timer.timeout.connect(self._flush_pin_persist)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self._autosave_current_stop)
        self._periodic_save = QTimer(self)
        self._periodic_save.timeout.connect(self._periodic_save_shift)
        self._map_health = QTimer(self)
        self._map_health.timeout.connect(self._map_health_check)
        self._power_timer = QTimer(self)
        self._power_timer.timeout.connect(self._poll_power)
        self._power_timer.start(30_000)
        self._apply_power_profile(force=True)

    def _init_map_view(self) -> None:
        ensure_qwebchannel_js()
        ok_web, web_msg = web_assets_ok()
        if not ok_web:
            QMessageBox.critical(
                self, "Map UI missing",
                f"{web_msg}\n\n"
                "The _internal folder must be next to TrafficDeployer.exe.\n"
                "Delete this folder, unzip TrafficDeployer-WorkLaptop.zip again, run OPEN_APP.bat.",
            )
        port = local_server.start(WEB_DIR, DATA_DIR)
        self.view = QWebEngineView()
        profile = QWebEngineProfile.defaultProfile()
        profile.setHttpCacheMaximumSize(web_http_cache_bytes())
        page = AppWebPage(profile, self.view)
        page.stopClicked.connect(self._on_stop_clicked)
        page.mapClicked.connect(self._on_map_clicked)
        self.view.setPage(page)
        self.bridge = MapBridge()
        self.bridge.bind_page(page)
        channel = QWebChannel()
        channel.registerObject("bridge", self.bridge)
        page.setWebChannel(channel)
        self.bridge.mapReady.connect(self._on_map_ready)
        self.bridge.mapClicked.connect(self._on_map_clicked)
        self.bridge.stopClicked.connect(self._on_stop_clicked)
        self.view.loadFinished.connect(self._on_page_load_finished)
        self._map_ready_polls = 0
        self._map_js_ready = False
        self.view.load(QUrl(f"http://127.0.0.1:{port}/index.html"))

    def _init_shell_ui(self) -> None:
        self._build_ui()
        self._setup_shortcuts()
        self._sync_theme_buttons()
        self._refresh_theme_labels()
        self._refresh_offline_ui()
        self._refresh_online_status()
        self._refresh_field_strip_ui()
        self._apply_field_nav_shell()
        self._refresh_file_lists()
        self._warn_missing_upload_paths()
        if self.state.stops:
            self._refresh_day_filter()
            self._update_right(force_map=True)
            self.statusBar().showMessage(
                f"{APP_NAME} v{APP_VERSION} — resumed {len(self.state.stops)} stops "
                f"(profile {self.state.profile})", 10000)
        else:
            self.statusBar().showMessage(
                f"{APP_NAME} v{APP_VERSION} — ready (profile {self.state.profile})", 8000)

    def _init_gps_and_deferred_refresh(self) -> None:
        self.gps = gps_reader.GPSStream()
        self.gps.start()
        self.gps_timer = QTimer(self)
        self.gps_timer.timeout.connect(self._tick_gps)
        self._sync_gps_timer()

        if self._work_laptop:
            QTimer.singleShot(800, lambda: self.statusBar().showMessage(
                "Loading map — first open on 4 GB laptop can take 3–5 min. Leave plugged in.",
                20_000,
            ))
            QTimer.singleShot(8000, self._refresh_field_ready)
        else:
            QTimer.singleShot(800, self._refresh_field_ready)
        QTimer.singleShot(900, self._refresh_map_preview)
        QTimer.singleShot(1200, self._poll_power)
        QTimer.singleShot(2500, self._maybe_field_startup_dialog)
        if not self.state.offline_mode:
            QTimer.singleShot(600, self._refresh_online_status)
        if self.state.offline_mode:
            self.statusBar().showMessage(
                "Field mode (offline) — at home with Wi‑Fi? Tap Online in the top bar.",
                14000,
            )
