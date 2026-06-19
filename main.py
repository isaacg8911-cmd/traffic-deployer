"""Traffic Deployer - desktop app (PySide6).

A Streets-&-Trips-style window: native side panels + an embedded offline
California map. Keeps every existing tool (USB GPS, .EST/Excel ingest, encrypted
save) and routes on the real road network (origin → stops → origin).

Run:  python main.py     (START.bat does the venv + launch for you)
"""
from __future__ import annotations

import os
import sys

# Stabilize Qt WebEngine on Windows GPUs that drop the D3D context ("context lost
# during MakeCurrent"). MapLibre NEEDS WebGL, so we must NOT use --disable-gpu
# (that kills WebGL and the map goes blank). Instead route GL through ANGLE's
# SwiftShader (software) backend: working WebGL that's stable on any machine.
# Must be set before any QtWebEngine import.
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader "
    "--ignore-gpu-blocklist --disable-background-timer-throttling"
)

import json
import math
import shutil

from PySide6.QtCore import Qt, QTimer, QUrl, QThread
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QShortcut
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QSplitter, QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
    QDoubleSpinBox, QProgressDialog, QScrollArea, QSizePolicy,
)

import gps_reader
import local_server
import road_router
from bridge import MapBridge
from core import connectivity, export, geo, ingest, maps_links, offline_policy, setup_network, validate
from core import direction as direction_rules
from core import field_alerts
from core import install_checklist
from core import power as laptop_power
from core.setup_checklist import evaluate as setup_checklist_eval
from core.setup_checklist import route_summary as build_route_summary
from core.field_ready import TOMORROW_STEPS, check_all
from core.offline_gate import evaluate as offline_gate_eval
from core.state import RouteState, ca_now
from ui.paths import (
    APP_DIR, COUNTER_DOWNLOAD_DIR, DATA_DIR, DEMO_CSV, DEMO_DIR, DEMO_EST, DIRECTIONS,
    IS_PORTABLE, LAUNCH_HINT, UNDO_FIELDS, VENDOR_DIR, WEB_DIR, web_assets_ok,
)
from ui.route_pick_dialog import RoutePickOrderDialog
from ui.threads import (
    DownloadRoadsThread, GeocodeThread, MapSetupThread, PicocountThread,
    RouteApplyPickThread, RouteOptimizeThread, SmokeTestThread,
)
from core import picocount
from core import crash_log
from ui.web_page import AppWebPage, ensure_qwebchannel_js
from ui import workflow as setup_workflow
from ui.pages import audit_page, install_page, pickup_page, route_page, setup_page
from ui.setup_wizard import SetupWizard
from ui.simple_mode import (
    BUILD_LABEL,
    FIELD_NAV_INDICES,
    FIELD_SHELL,
    GPS_PUSH_HEARTBEAT_S,
    GPS_PUSH_MIN_M,
    GPS_TICK_DRIVE_MS,
    GPS_TICK_MS,
    HIDE_PANEL_THEMES,
    MAP_HEALTH_DRIVE_MS,
    MAP_HEALTH_FIELD_MS,
    MAP_HEALTH_MS,
    SIMPLE_MODE,
    timing_profile,
)
from ui.counter_ui import apply_counter_panel_connected, apply_counter_status
from ui.widgets import section_group, stat_card
from core.shift_summary import summarize as shift_summarize
from ui_themes import normalize_theme, qt_stylesheet
from version import APP_NAME, APP_VERSION, APP_TAGLINE


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1320, 860)
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
        page = AppWebPage(QWebEngineProfile.defaultProfile(), self.view)
        page.stopClicked.connect(self._on_stop_clicked)
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

        self.gps = gps_reader.GPSStream()
        self.gps.start()
        self.gps_timer = QTimer(self)
        self.gps_timer.timeout.connect(self._tick_gps)
        self._sync_gps_timer()

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

    def _internet_allowed(self) -> bool:
        """Online features (address search, road download) only before Ready for Offline."""
        return not self.state.offline_mode

    def _sync_field_mode(self) -> None:
        """Keep geo/connectivity aligned with offline_mode (no public internet on road)."""
        offline_policy.set_field_mode(bool(self.state.offline_mode))

    def _poll_power(self) -> None:
        snap = laptop_power.read_power()
        prev = self._power_on_ac
        self._power_on_ac = snap.on_ac
        self._power_label = snap.label
        if hasattr(self, "status_power"):
            if snap.on_ac is False:
                self.status_power.setText("Battery saver")
                self.status_power.setToolTip(
                    f"Laptop on battery ({snap.label}) — GPS/map throttled to save power. "
                    "Plug in for full refresh rate.")
            elif snap.on_ac is True:
                self.status_power.setText("Plugged in")
                self.status_power.setToolTip(f"AC power ({snap.label}) — full GPS/map rate.")
            else:
                self.status_power.setText("")
                self.status_power.setToolTip("")
        if prev != snap.on_ac:
            self._apply_power_profile(force=True)
            if snap.on_ac is False:
                self.statusBar().showMessage(
                    "Battery saver on — plug in for full GPS/map rate.", 8000)
            elif snap.on_ac is True and prev is False:
                self.statusBar().showMessage("Plugged in — full GPS/map rate restored.", 6000)

    def _apply_power_profile(self, *, force: bool = False) -> None:
        t = timing_profile(on_ac=self._power_on_ac, gps_follow=self._gps_follow)
        self._gps_push_min_m = t["gps_push_min_m"]
        self._gps_push_heartbeat_s = t["gps_push_heartbeat_s"]
        self._strip_throttle_s = t["strip_throttle_s"]
        self._sync_gps_timer()
        self._sync_map_health_interval()
        if hasattr(self, "_periodic_save"):
            ms = int(t["periodic_save_ms"])
            if force or self._periodic_save.interval() != ms:
                self._periodic_save.setInterval(ms)
                if not self._periodic_save.isActive():
                    self._periodic_save.start(ms)

    def _sync_gps_timer(self) -> None:
        if not hasattr(self, "gps_timer"):
            return
        t = timing_profile(on_ac=self._power_on_ac, gps_follow=self._gps_follow)
        ms = int(t["gps_tick_ms"])
        if self.gps_timer.interval() != ms:
            self.gps_timer.setInterval(ms)
        if not self.gps_timer.isActive():
            self.gps_timer.start(ms)

    def _sync_map_health_interval(self) -> None:
        if not hasattr(self, "_map_health"):
            return
        t = timing_profile(on_ac=self._power_on_ac, gps_follow=self._gps_follow)
        if self._gps_follow:
            ms = int(t["map_health_drive_ms"])
        elif self.state.offline_mode:
            ms = int(t["map_health_field_ms"])
        else:
            ms = int(t["map_health_ms"])
        if self._map_health.interval() != ms:
            self._map_health.setInterval(ms)
        if not self._map_health.isActive():
            self._map_health.start(ms)

    def _should_push_gps_bridge(
        self, lat: float, lon: float, heading: float | None,
    ) -> bool:
        import time as _time

        now = _time.time()
        last = self._last_gps_bridge
        if last is None:
            return True
        if now - self._last_gps_bridge_t >= self._gps_push_heartbeat_s:
            return True
        llat, llon, lhdg = last
        if self._moved((llat, llon), (lat, lon), min_m=self._gps_push_min_m):
            return True
        if heading is not None and lhdg is not None:
            delta = abs(((heading - lhdg) + 180) % 360 - 180)
            if delta >= 12.0:
                return True
        return False

    def _apply_field_nav_shell(self) -> None:
        """Hide Setup/Audit in nav when offline field shell is active."""
        if not FIELD_SHELL:
            return
        on_field = bool(self.state.offline_mode)
        for i in range(5):
            btn = getattr(self, f"_navbtn_{i}", None)
            if btn is None:
                continue
            if on_field:
                btn.setVisible(i in FIELD_NAV_INDICES)
            else:
                btn.setVisible(True)
        if on_field and self.pages.currentIndex() not in FIELD_NAV_INDICES:
            self._go_page(1)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        side = QWidget()
        side.setObjectName("sidepanel")
        side.setMinimumWidth(360)
        side.setMaximumWidth(440)
        side.setAutoFillBackground(True)
        side.setAttribute(Qt.WA_StyledBackground, True)
        self._side_panel = side
        side_lay = QHBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.setSpacing(0)

        nav = QWidget()
        nav.setObjectName("navRail")
        nav.setFixedWidth(64)
        nav_lay = QVBoxLayout(nav)
        nav_lay.setContentsMargins(6, 12, 6, 12)
        nav_lay.setSpacing(4)
        self._nav_labels = ("Setup", "Route", "Install", "Pickup", "Audit")
        for idx, label in enumerate(self._nav_labels):
            b = QPushButton(label)
            b.setObjectName("navBtn")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, i=idx: self._go_page(i))
            nav_lay.addWidget(b)
            setattr(self, f"_navbtn_{idx}", b)
        self._navbtn_0.setChecked(True)
        nav_lay.addStretch(1)
        side_lay.addWidget(nav)

        pages_col = QWidget()
        pages_col.setObjectName("pagesColumn")
        pages_col.setMinimumWidth(320)
        pages_lay = QVBoxLayout(pages_col)
        pages_lay.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._wrap_scroll(setup_page.build_setup_page(self)))   # 0
        self.pages.addWidget(self._wrap_scroll(route_page.build_route_page(self)))   # 1
        self.pages.addWidget(self._wrap_scroll(install_page.build_install_page(self)))  # 2
        self.pages.addWidget(self._wrap_scroll(pickup_page.build_pickup_page(self)))     # 3
        self.pages.addWidget(self._wrap_scroll(audit_page.build_audit_page(self)))      # 4
        pages_lay.addWidget(self.pages)
        side_lay.addWidget(pages_col, 1)

        map_frame = QFrame()
        map_frame.setObjectName("mapFrame")
        map_frame.setFrameShape(QFrame.NoFrame)
        map_frame.setAutoFillBackground(True)
        map_frame.setAttribute(Qt.WA_StyledBackground, True)
        map_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        map_lay = QVBoxLayout(map_frame)
        map_lay.setContentsMargins(0, 0, 0, 0)
        map_lay.setSpacing(0)
        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(self._placeholder())  # 0
        self.view.setParent(None)
        self.right_stack.addWidget(self.view)            # 1
        map_lay.addWidget(self.right_stack)
        self._map_frame = map_frame

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setObjectName("mainSplit")
        self._splitter.setChildrenCollapsible(False)
        self._splitter.addWidget(side)
        self._splitter.addWidget(map_frame)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([400, 920])
        body.addWidget(self._splitter, 1)

        wrap = QWidget()
        wrap.setLayout(body)
        root.addWidget(wrap, 1)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())
        self.status_gps = QLabel("GPS: searching...")
        self.status_power = QLabel("")
        self.status_route = QLabel("")
        self.statusBar().addWidget(self.status_gps)
        self.statusBar().addPermanentWidget(self.status_power)
        self.statusBar().addPermanentWidget(self.status_route)
        self._refresh_origin_label()
        self._refresh_workflow_strip()
        self._update_right()
        if hasattr(self, "lbl_pick_status"):
            self._refresh_route_pick_ui()

    def _sync_prefs_ui(self) -> None:
        """No voice/theme prefs on route page after voice removal."""
        return

    def _wrap_scroll(self, w: QWidget) -> QWidget:
        sc = QScrollArea()
        sc.setObjectName("pageScroll")
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setFrameShape(QFrame.NoFrame)
        w.setMinimumWidth(300)
        sc.setWidget(w)
        return sc

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_side_panel"):
            self._side_panel.raise_()

    def _placeholder(self) -> QWidget:
        w = QWidget()
        w.setObjectName("placeholder")
        v = QVBoxLayout(w)
        v.setContentsMargins(48, 48, 48, 48)
        v.addStretch(1)
        t = QLabel(APP_NAME)
        t.setObjectName("phTitle")
        t.setAlignment(Qt.AlignCenter)
        sub = QLabel(APP_TAGLINE)
        sub.setObjectName("phSub")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        v.addWidget(t)
        v.addSpacing(6)
        v.addWidget(sub)
        v.addSpacing(24)
        for text in (
            "1  Set your start (GPS, address, or coordinates)",
            "2  Add Excel + .EST, download road map",
            "3  Build optimized route — map appears here",
        ):
            step = QLabel(text)
            step.setObjectName("phStep")
            step.setAlignment(Qt.AlignCenter)
            v.addWidget(step)
            v.addSpacing(8)
        v.addStretch(1)
        return w

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 6, 12, 6)
        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand = QLabel(APP_NAME)
        brand.setObjectName("brand")
        self.brand_sub = QLabel(f"v{APP_VERSION}  ·  home setup · Wi‑Fi tools on")
        self.brand_sub.setObjectName("brandSub")
        brand_col.addWidget(brand)
        brand_col.addWidget(self.brand_sub)
        lay.addLayout(brand_col)
        lay.addStretch(1)

        mode_wrap = QWidget()
        mode_wrap.setObjectName("modeBar")
        mode_lay = QHBoxLayout(mode_wrap)
        mode_lay.setContentsMargins(0, 0, 0, 0)
        mode_lay.setSpacing(6)
        self.lbl_mode_pill = QLabel("ONLINE")
        self.lbl_mode_pill.setObjectName("modePill")
        self.btn_mode_online = QPushButton("I'm online")
        self.btn_mode_online.setObjectName("modeBtnOnline")
        self.btn_mode_online.setCheckable(True)
        self.btn_mode_online.clicked.connect(self._on_mode_online)
        self.btn_mode_offline = QPushButton("Go offline")
        self.btn_mode_offline.setObjectName("modeBtnOffline")
        self.btn_mode_offline.setCheckable(True)
        self.btn_mode_offline.clicked.connect(self._on_mode_offline)
        mode_lay.addWidget(self.lbl_mode_pill)
        mode_lay.addWidget(self.btn_mode_online)
        mode_lay.addWidget(self.btn_mode_offline)
        lay.addWidget(mode_wrap)
        lay.addSpacing(8)
        self.btn_drive_arrived = QPushButton("ARRIVED → Install")
        self.btn_drive_arrived.setObjectName("driveArrived")
        self.btn_drive_arrived.clicked.connect(self._drive_arrived_install)
        self.btn_drive_arrived.hide()
        lay.addWidget(self.btn_drive_arrived)
        self.btn_drive_end = QPushButton("Stop driving")
        self.btn_drive_end.setObjectName("secondary")
        self.btn_drive_end.clicked.connect(self._stop_drive)
        self.btn_drive_end.hide()
        lay.addWidget(self.btn_drive_end)
        lay.addSpacing(8)

        b_about = QPushButton("About")
        b_about.setObjectName("aboutBtn")
        b_about.clicked.connect(self._show_about)
        lay.addWidget(b_about)
        lay.addSpacing(12)
        theme_wrap = QWidget()
        theme_wrap.setObjectName("themeBar")
        theme_lay = QHBoxLayout(theme_wrap)
        theme_lay.setContentsMargins(0, 0, 0, 0)
        theme_lay.setSpacing(4)
        self._theme_btns: dict[str, QPushButton] = {}
        for key, label in (("sunny", "Sunny"), ("cloudy", "Cloudy"), ("night", "Night")):
            tb = QPushButton(label)
            tb.setObjectName("themeBtn")
            tb.setCheckable(True)
            tb.clicked.connect(lambda _=False, k=key: self._set_view_theme(k))
            theme_lay.addWidget(tb)
            self._theme_btns[key] = tb
        self._theme_wrap = theme_wrap
        if HIDE_PANEL_THEMES:
            theme_wrap.hide()
        lay.addWidget(theme_wrap)
        from ui.simple_mode import COMPACT_UI
        if COMPACT_UI:
            self.brand_sub.hide()
        return bar

    def _show_about(self):
        maps = "Yes" if os.path.isfile(os.path.join(DATA_DIR, "california.pmtiles")) else "No — run setup_maps.py"
        roads = "Yes" if road_router.has_graph(DATA_DIR) else "No — download in Setup"
        QMessageBox.information(
            self, APP_NAME,
            f"<b>{APP_NAME} v{APP_VERSION}</b><br><br>"
            f"{APP_TAGLINE}<br><br>"
            f"<b>Offline basemap:</b> {maps}<br>"
            f"<b>Road routing graph:</b> {roads}<br><br>"
            f"Profile: {self.state.profile}<br>"
            f"Smoke test: <code>scripts\\smoke.bat</code>",
        )

    def _go_page(self, i: int):
        if FIELD_SHELL and self.state.offline_mode and i not in FIELD_NAV_INDICES:
            self.statusBar().showMessage(
                "Field mode — Route, Install, Pickup, Audit. Tap I'm online at home for Setup.",
                5000,
            )
            return
        if self._gps_follow and i not in (1, 2):
            self.statusBar().showMessage(
                "Following GPS — tap ARRIVED or Stop follow first.", 5000)
            return
        if self.pages.currentIndex() == 2 and i != 2:
            self._flush_install_form()
            self._end_manual_grab(silent=True)
        self.pages.setCurrentIndex(i)
        for j in range(5):
            getattr(self, f"_navbtn_{j}").setChecked(j == i)
        if i == 0:
            self.spin_lat.setValue(self.state.home[0])
            self.spin_lon.setValue(self.state.home[1])
            self._refresh_workflow_strip()
        elif i == 1:
            self._refresh_route_list()
        elif i == 2:
            self._counter_list_ports()
            self._refresh_install()
            QTimer.singleShot(350, self._counter_auto_connect)
        elif i == 3:
            self._refresh_pickup()
        elif i == 4:
            self._refresh_audit()
        self._refresh_field_alerts()
        self._update_right()
        self._push_state()

    def _update_right(self, force_map: bool = False):
        show_map = (
            force_map
            or self._gps_follow
            or bool(self.state.stops)
            or bool(getattr(self, "_map_preview_stops", None))
        )
        was_hidden = self.right_stack.currentIndex() == 0
        self.right_stack.setCurrentIndex(1 if show_map else 0)
        if show_map and (was_hidden or force_map) and self.state.stops:
            QTimer.singleShot(250, self._refresh_map_view)

    def _refresh_workflow_strip(self):
        if SIMPLE_MODE or not getattr(self, "workflow_strip", None):
            return
        miles = float(self.state.route.get("miles", 0) or 0)
        self.workflow_strip.set_steps(setup_workflow.compute_workflow(
            home=tuple(self.state.home),
            default_home=self.state.default_home,
            excel_paths=self.excel_paths,
            est_paths=self.est_paths,
            has_graph=road_router.has_graph(DATA_DIR),
            route_miles=miles,
            offline_mode=bool(self.state.offline_mode),
        ))

    def _refresh_field_ready(self):
        if not hasattr(self, "lbl_field_score"):
            return
        gps_snap = self.gps.latest() if hasattr(self, "gps") else None
        r = check_all(
            APP_DIR,
            probe_gps=gps_snap is None,
            probe_counter=True,
            gps_snapshot=gps_snap,
            stop_server_after=False,
        )
        score = r["score"]
        from ui.simple_mode import COMPACT_UI
        if score >= 88:
            color, tag = "#15803d", "READY FOR FIELD"
        elif score >= 70:
            color, tag = "#b45309", "READY WITH WARNINGS"
        else:
            color, tag = "#b91c1c", "FIX BEFORE FIELD"
        if COMPACT_UI:
            self.lbl_field_score.setText(f"{tag} · {score}/100")
            self.lbl_field_score.setStyleSheet(
                f"font-weight:800;font-size:13px;color:{color};")
            bad = [it for it in r["items"] if it["level"] != "ok"]
            if bad:
                lines = [
                    f"{'✗' if it['level'] == 'fail' else '!'} {it['label']}"
                    for it in bad[:5]
                ]
            else:
                lines = ["✓ All checks passed"]
        else:
            self.lbl_field_score.setText(f"{tag} — {score}/100")
            self.lbl_field_score.setStyleSheet(
                f"font-weight:800;font-size:15px;color:{color};")
            lines = []
            for it in r["items"]:
                if it["level"] == "ok":
                    sym = "✓"
                elif it["level"] == "warn":
                    sym = "!"
                else:
                    sym = "✗"
                extra = f" — {it['detail']}" if it.get("detail") and it["level"] != "ok" else ""
                lines.append(f"{sym} {it['label']}{extra}")
        self.lbl_field_checks.setText("\n".join(lines))
        self._field_report = r
        self._refresh_workflow_strip()
        self._refresh_field_strip_ui()

    def _maybe_field_startup_dialog(self):
        if self.state.offline_mode and self.state.stops:
            return
        r = getattr(self, "_field_report", None) or check_all(APP_DIR, probe_gps=True)
        if r.get("fail_count", 0) == 0:
            if r.get("warn_count", 0) and not self.state.stops:
                self.statusBar().showMessage(
                    "Field readiness: warnings on Setup tab — review before you leave.", 12000)
            return
        crit = [i for i in r["items"] if i["level"] == "fail"]
        body = "\n".join(f"• {i['label']}: {i.get('detail', 'missing')}" for i in crit)
        QMessageBox.warning(
            self, "Fix before field",
            f"Critical items need attention:\n\n{body}\n\n"
            "Open Setup → Field Readiness for details.\n"
            + (
                "Map 404? Re-extract the full zip — _internal/web must be beside the exe."
                if IS_PORTABLE
                else "Run setup_maps.py on WiFi if the offline map is missing."
            ),
        )

    def _run_smoke_test(self):
        if getattr(self, "_smoke_thread", None) and self._smoke_thread.isRunning():
            self.statusBar().showMessage("Smoke test already running…", 3000)
            return
        self.statusBar().showMessage("Running smoke test… (app stays responsive)", 5000)
        thread = SmokeTestThread()
        self._smoke_thread = thread

        def done(code: int, out: str):
            self._smoke_thread = None
            if code == 0:
                self._info("Smoke test PASSED.\n\n" + out[-1200:])
                self.statusBar().showMessage("Smoke test passed.", 6000)
            else:
                self._warn("Smoke test FAILED.\n\n" + out[-2000:])
            self._refresh_field_ready()

        thread.finished_result.connect(done)
        thread.start()

    # --- Route / Install / Setup pages: ui/pages/* (P46 slim)

    @staticmethod
    def _h(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("role", "h")
        return lbl

    # ------------------------------------------------------ map / state push
    def _on_page_load_finished(self, ok: bool):
        if not ok:
            return
        self._map_ready_polls = 0
        self._poll_map_ready()

    def _poll_map_ready(self):
        def cb(ready):
            if ready:
                if not self._map_js_ready:
                    self._map_js_ready = True
                    self._on_map_ready()
            elif self._map_ready_polls < 150:
                self._map_ready_polls += 1
                QTimer.singleShot(200, self._poll_map_ready)
        self.view.page().runJavaScript("!!window.__mapLoaded", cb)

    def _on_map_ready(self):
        self.bridge.set_follow(False)
        if self.state.stops:
            self._apply_map_startup_view()

    def _shift_has_field_progress(self) -> bool:
        return any(
            s.get("installed") or s.get("skipped") or s.get("picked_up")
            for s in self.state.stops
        )

    def _map_focus_coords(self) -> tuple[float, float] | None:
        """Most recent install/skip/pickup field point, else current stop."""
        last: tuple[float, float] | None = None
        for s in self.state.stops:
            if not (s.get("installed") or s.get("skipped") or s.get("picked_up")):
                continue
            if s.get("field_lat") is not None and s.get("field_lon") is not None:
                last = (float(s["field_lat"]), float(s["field_lon"]))
            else:
                anchor = self._stop_anchor_coords(s)
                if anchor:
                    last = anchor
        if last:
            return last
        if self.state.stops and self.current_index < len(self.state.stops):
            lat, lon = self.state.point(self.state.stops[self.current_index])
            return float(lat), float(lon)
        items = self._installed_stops()
        if items:
            s = items[min(self.pickup_index, len(items) - 1)]
            if s.get("field_lat") is not None and s.get("field_lon") is not None:
                return float(s["field_lat"]), float(s["field_lon"])
            anchor = self._stop_anchor_coords(s)
            if anchor:
                return anchor
        return None

    def _apply_map_startup_view(self) -> None:
        """Fit all sites on fresh route; after field work, zoom to last action."""
        if not self.state.stops:
            return
        self.bridge.refresh_view()
        if self._shift_has_field_progress():
            self._push_state(fit=False)
            coords = self._map_focus_coords()
            if coords:
                lat, lon = coords
                QTimer.singleShot(350, lambda: self.bridge.fly_to(lat, lon, 14))
        else:
            self._push_state(fit=True)

    def _refresh_map_view(self):
        """Resize the WebEngine canvas (it starts at 0px while hidden) and redraw."""
        self.bridge.refresh_view()
        self._push_state(fit=True)

    def _display_route(self) -> dict:
        """Map shows precomputed next leg only — not the full tour polyline."""
        r = self.state.route or {}
        return {
            "polyline": [],
            "miles": r.get("miles", 0.0),
            "graph": r.get("graph", False),
        }

    def _ensure_site_legs(self) -> None:
        if not self.state.stops:
            return
        if self.state.route.get("site_legs"):
            return
        from core.routing import build_site_legs
        self.state.route["site_legs"] = build_site_legs(
            self.state.stops, tuple(self.state.home), DATA_DIR)

    def _first_pending_index(self) -> int | None:
        for i, s in enumerate(self.state.stops):
            if not s.get("installed") and not s.get("skipped"):
                return i
        return None

    def _next_leg_payload(self) -> dict | None:
        if not self.state.stops:
            return None
        route = self.state.route or {}
        if not route.get("site_legs") and float(route.get("miles") or 0) <= 0:
            return None
        self._ensure_site_legs()
        idx = self._first_pending_index()
        if idx is None:
            return None
        legs = route.get("site_legs") or []
        if idx >= len(legs):
            return None
        leg = legs[idx]
        poly = leg.get("polyline") or []
        if len(poly) < 2:
            return None
        target = self.state.stops[idx]
        from core.routing import _stop_pt, sanitize_leg_polyline

        dest = _stop_pt(target)
        if not geo.ca_coords_plausible(*self.state.home) or not geo.ca_coords_plausible(*dest):
            return None
        clean = sanitize_leg_polyline(poly, tuple(self.state.home), dest)
        if not clean or len(clean) < 2:
            return None
        return {
            "polyline": clean,
            "to_uid": target["uid"],
            "to_id": target.get("id"),
            "miles": float(leg.get("miles") or 0.0),
            "index": idx,
        }

    def _update_follow_banner(self) -> None:
        if not hasattr(self, "lbl_drive_banner"):
            return
        if not self._gps_follow:
            self.lbl_drive_banner.hide()
            return
        nxt = self._next_leg_payload()
        if not nxt:
            self.lbl_drive_banner.setText("All stops done.")
            self.lbl_drive_banner.show()
            return
        gi = nxt["index"]
        target = self.state.stops[gi]
        self.lbl_drive_banner.setText(
            f"Next: Site {nxt.get('to_id', '?')} — {nxt['miles']:.1f} mi  "
            f"({self._street_label(target)})")
        self.lbl_drive_banner.show()

    def _set_drive_mode(self, on: bool) -> None:
        if hasattr(self, "btn_drive_arrived"):
            self.btn_drive_arrived.setVisible(on)
            self.btn_drive_end.setVisible(on)
        if on:
            self._splitter_sizes_saved = self._splitter.sizes()
            total = max(800, sum(self._splitter_sizes_saved))
            self._splitter.setSizes([0, total])
            for box in getattr(self, "_route_fold_boxes", []):
                if box is not None:
                    box.hide()
            for i in range(5):
                btn = getattr(self, f"_navbtn_{i}", None)
                if btn is not None:
                    btn.setEnabled(i in (1, 2))
            self._update_follow_banner()
            self.brand_sub.setText("Following GPS — next site on map")
        else:
            if self._splitter_sizes_saved:
                self._splitter.setSizes(self._splitter_sizes_saved)
            for box in getattr(self, "_route_fold_boxes", []):
                if box is not None:
                    box.show()
            self._apply_field_nav_shell()
            for i in range(5):
                btn = getattr(self, f"_navbtn_{i}", None)
                if btn is not None:
                    if FIELD_SHELL and self.state.offline_mode:
                        btn.setEnabled(i in FIELD_NAV_INDICES)
                    else:
                        btn.setEnabled(True)
            self.lbl_drive_banner.hide()
            self.brand_sub.setText(
                f"v{APP_VERSION}  ·  field mode" if self.state.offline_mode
                else f"v{APP_VERSION}  ·  home setup · Wi‑Fi tools on")
        self._sync_gps_timer()
        self._sync_map_health_interval()

    def _drive_arrived_install(self) -> None:
        if not self._gps_follow:
            return
        self._go_page(2)
        self._center_current()

    def _on_day_filter_changed(self):
        if hasattr(self, "combo_day"):
            self.state.map_day_filter = self.combo_day.currentText()
            self.state.save()
        self._push_state()

    def _refresh_day_filter(self):
        if not hasattr(self, "combo_day"):
            return
        cur = self.state.map_day_filter or self.combo_day.currentText()
        self.combo_day.blockSignals(True)
        self.combo_day.clear()
        self.combo_day.addItem("All maps")
        for label in self.state.active_files or sorted({s.get("sheet", "") for s in self.state.stops}):
            if label and self.combo_day.findText(label) < 0:
                self.combo_day.addItem(label)
        idx = self.combo_day.findText(cur)
        self.combo_day.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_day.blockSignals(False)
        self.state.map_day_filter = self.combo_day.currentText()

    def _stops_for_map(self) -> list[dict]:
        base = self.state.stops or getattr(self, "_map_preview_stops", []) or []
        if not hasattr(self, "combo_day"):
            filtered = base
        else:
            day = self.combo_day.currentText()
            if day == "All maps":
                filtered = base
            else:
                filtered = [s for s in base if s.get("sheet") == day]
        if self._route_pick_mode:
            return [dict(s) for s in filtered]
        return self._stops_with_seq(filtered)

    @staticmethod
    def _site_letter(index: int) -> str:
        """A, B, … Z, AA — stable label per site during map pick."""
        n = index
        letters = ""
        while True:
            letters = chr(ord("A") + (n % 26)) + letters
            n = n // 26 - 1
            if n < 0:
                break
        return letters

    def _pick_site_letters(self) -> dict[str, str]:
        return {s["uid"]: self._site_letter(i) for i, s in enumerate(self.state.stops)}

    def _pick_prompt_text(self) -> str:
        n = len(self._route_pick_uids)
        total = len(self.state.stops)
        if n >= total:
            return f"All {total} sites chosen — tap Apply route"
        return f"Click stop {n + 1} of {total} on the map"

    def _pick_waiting_hint(self) -> str:
        n = len(self._route_pick_uids)
        total = len(self.state.stops)
        if n >= total:
            return "ready for Apply"
        return "waiting for your click — blue begin or red end"

    @staticmethod
    def _parse_stop_click(raw: str) -> tuple[str, str | None]:
        if "|" in raw:
            uid, side = raw.split("|", 1)
            if side in ("begin", "end"):
                return uid, side
        return raw, None

    @staticmethod
    def _apply_pick_side(stop: dict, side: str) -> None:
        if side == "begin":
            stop["cross_lat"] = stop["begin_lat"]
            stop["cross_lon"] = stop["begin_lon"]
        else:
            stop["cross_lat"] = stop["end_lat"]
            stop["cross_lon"] = stop["end_lon"]
        stop["cross_side"] = side
        stop["pick_cross_locked"] = True

    def _ask_route_build_mode(self) -> str | None:
        box = QMessageBox(self)
        box.setWindowTitle("Build route")
        box.setText("How should stop order be chosen?")
        box.setInformativeText(
            "Pick route: tap blue or red on each site for stop order and drive-to end.\n"
            "Auto-optimize: the app picks the best order on real streets.")
        btn_pick = box.addButton("Pick route on map", QMessageBox.AcceptRole)
        btn_opt = box.addButton("Auto-optimize", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked == btn_pick:
            return "pick"
        if clicked == btn_opt:
            return "optimize"
        return None

    @staticmethod
    def _stops_with_seq(stops: list[dict]) -> list[dict]:
        """Route visit order → map labels 1, 2, 3…"""
        out = []
        for i, s in enumerate(stops):
            d = dict(s)
            d["seq"] = i + 1
            out.append(d)
        return out

    def _refresh_map_preview(self):
        """Show every site begin/end line as soon as Excel + .EST are loaded (before BUILD ROUTE)."""
        if self.state.stops:
            self._map_preview_stops = []
            self._map_preview_route = {"polyline": [], "miles": 0.0, "graph": False}
            return
        if not self.excel_paths or not self.est_paths:
            self._map_preview_stops = []
            self._map_preview_route = {"polyline": [], "miles": 0.0, "graph": False}
            self._update_right()
            if self._map_js_ready:
                self._push_state()
            return
        try:
            from core import routing
            sites = ingest.parse_excel_sites(self.excel_paths)
            raw = ingest.match_est_files(self._est_configs(), sites, self.state.home)
            self._map_preview_stops = routing.assign_crossings_for_display(
                raw, self.state.home, DATA_DIR)
            self._map_preview_route = {"polyline": [], "miles": 0.0, "graph": False}
        except Exception:
            self._map_preview_stops = []
            self._map_preview_route = {"polyline": [], "miles": 0.0, "graph": False}
        self._update_right(force_map=bool(self._map_preview_stops))
        if self._map_js_ready:
            self._push_state(fit=bool(self._map_preview_stops))

    def _warn_missing_upload_paths(self):
        saved_e = len(getattr(self.state, "excel_paths", []) or [])
        saved_m = len(getattr(self.state, "est_paths", []) or [])
        have_e, have_m = len(self.excel_paths), len(self.est_paths)
        if saved_e > have_e or saved_m > have_m:
            self.statusBar().showMessage(
                "Saved file list is incomplete — some Excel/EST paths moved. "
                "Re-add files on Setup.", 15000)

    def _route_for_map(self, *, preview: bool) -> dict:
        if preview:
            return getattr(self, "_map_preview_route", None) or {"polyline": [], "graph": False}
        return self._display_route()

    def _push_state(self, fit: bool = False):
        following = bool(self._gps_follow)
        preview = bool(self._map_preview_stops) and not self.state.stops
        picking = bool(self._route_pick_mode)
        manual_grab = bool(self._manual_grab_mode)
        nxt = self._next_leg_payload()
        if manual_grab:
            mode = "manual_grab"
        elif picking:
            mode = "pick"
        elif following:
            mode = "drive"
        elif preview:
            mode = "preview"
        else:
            mode = "plan"
        hi = self._highlight_stop_uid()
        on_setup = self.pages.currentIndex() == 0
        st = {
            "theme": self.state.theme,
            "home": list(self.state.home),
            "stops": self._stops_for_map(),
            "route": self._route_for_map(preview=preview),
            "next_leg": nxt,
            "fit": fit,
            "driving": following,
            "map_mode": mode,
            "highlight_uid": hi,
            "drive_target_uid": hi if nxt else None,
            "pick_order": list(self._route_pick_uids) if picking else [],
            "pick_prompt": self._manual_grab_prompt() if manual_grab else (
                self._pick_prompt_text() if picking else ""),
            "pick_waiting": self._pick_waiting_hint() if picking else "",
            "pick_letters": self._pick_site_letters() if picking else {},
            "show_segments": self.chk_show_segments.isChecked(),
            "show_badges": not picking,
            "show_guide": False,
            "lean_drive": following and bool(self.state.offline_mode),
        }
        self.bridge.send_state(st)
        miles = self.state.route.get("miles", 0.0)
        drive = (miles / 30.0) * 60 if miles else 0
        self.status_route.setText(f"Stops: {len(self.state.stops)}   Route: {miles:.1f} mi   ~{drive:.0f} min")
        if nxt and not following:
            self.status_route.setText(
                f"Next: Site {nxt.get('to_id', '?')} — {nxt['miles']:.1f} mi"
                f"   ({len(self.state.stops)} stops total)")

    @staticmethod
    def _stop_anchor_coords(s: dict) -> tuple[float, float] | None:
        clat, clon = s.get("cross_lat"), s.get("cross_lon")
        if clat is not None and clon is not None:
            return float(clat), float(clon)
        lat, lon = s.get("lat"), s.get("lon")
        if lat is not None and lon is not None:
            return float(lat), float(lon)
        return None

    def _nearest_unpicked_stop(
        self, lat: float, lon: float, *, max_m: float = 750.0,
    ) -> tuple[str | None, str | None]:
        from road_router import _haversine_m

        picked = set(self._route_pick_uids)
        best_uid: str | None = None
        best_side: str | None = None
        best_d = max_m
        for s in self.state.stops:
            uid = str(s.get("uid") or "")
            if not uid or uid in picked:
                continue
            candidates: list[tuple[tuple[float, float], str | None]] = []
            bl, blo = s.get("begin_lat"), s.get("begin_lon")
            if bl is not None and blo is not None:
                candidates.append(((float(bl), float(blo)), "begin"))
            el, elo = s.get("end_lat"), s.get("end_lon")
            if el is not None and elo is not None:
                candidates.append(((float(el), float(elo)), "end"))
            for pt, side in candidates:
                d = _haversine_m(lat, lon, pt[0], pt[1])
                if d < best_d:
                    best_d = d
                    best_uid = uid
                    best_side = side
        return best_uid, best_side

    def _on_map_clicked(self, lat: float, lon: float) -> None:
        if self._manual_grab_mode:
            self._manual_grab_at(lat, lon)
            return
        if not self._route_pick_mode:
            return
        uid, side = self._nearest_unpicked_stop(lat, lon)
        if uid:
            self._route_pick_add(uid, side=side)

    def _on_stop_clicked(self, uid: str):
        uid, side = self._parse_stop_click(uid)
        if self._route_pick_mode:
            self._route_pick_add(uid, side=side)
            return
        idx = self.state.index_of(uid)
        if idx >= 0:
            self.current_index = idx
            self._go_page(2)
            self._center_current()

    # ------------------------------------------------------------ GPS tick
    def _tick_gps(self):
        g = self.gps.latest()
        if g.get("fix") and g.get("lat") is not None:
            lat, lon = g["lat"], g["lon"]
            hdg = g.get("heading_display") or g.get("heading_locked") or g.get("heading")
            if self._should_push_gps_bridge(lat, lon, hdg):
                import time as _time
                self.bridge.send_gps({
                    "lat": lat, "lon": lon, "heading": hdg,
                    "heading_mode": g.get("heading_mode"), "speed_mps": g.get("speed_mps"),
                })
                self._last_gps_bridge = (lat, lon, hdg)
                self._last_gps_bridge_t = _time.time()
            self._update_compass_labels(g)
            self.status_gps.setText(f"GPS: FIX  {g.get('satellites', 0)} sats   {lat:.5f}, {lon:.5f}")
            if self._gps_follow:
                self._update_follow_banner()
            if hasattr(self, "lbl_field_score") and not hasattr(self, "_gps_ready_refreshed"):
                self._gps_ready_refreshed = True
                self._refresh_field_ready()
            self._maybe_refresh_field_strip()
        elif g.get("connected"):
            self.status_gps.setText(f"GPS: searching... {g.get('satellites', 0)} sats (need clear sky)")
            self._maybe_refresh_field_strip()
        else:
            self.status_gps.setText("GPS: not detected (check USB receiver)")
            self._maybe_refresh_field_strip()

    @staticmethod
    def _moved(a, b, min_m: float = 4.0) -> bool:
        return MainWindow._dist_m(a[0], a[1], b[0], b[1]) >= min_m

    @staticmethod
    def _heading_cardinal(deg: float | None) -> str:
        if deg is None:
            return "—"
        dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        return dirs[int(((deg + 22.5) % 360) / 45)]

    def _update_compass_labels(self, g: dict):
        hdg = g.get("heading_display") or g.get("heading_locked") or g.get("heading")
        mode = g.get("heading_mode") or "none"
        from ui.simple_mode import COMPACT_UI
        if hdg is None:
            txt = "No heading — drive briefly, then stop."
            sub = ""
        else:
            card = self._heading_cardinal(hdg)
            txt = f"{hdg:.0f}° ({card})"
            if COMPACT_UI:
                sub = ""
            elif mode == "locked":
                sub = "Stopped — locked heading (use for install direction)"
            elif mode == "moving":
                sub = "Moving — live GPS course"
            else:
                sub = "Slow/stop — averaging recent heading"
        if hasattr(self, "lbl_compass"):
            self.lbl_compass.setText(txt)
        if hasattr(self, "lbl_compass_sub") and self.lbl_compass_sub.parent():
            self.lbl_compass_sub.setText(sub)

    @staticmethod
    def _dist_m(lat1, lon1, lat2, lon2) -> float:
        dlat = (lat2 - lat1) * 111320.0
        dlon = (lon2 - lon1) * 111320.0 * math.cos(math.radians(lat1))
        return (dlat * dlat + dlon * dlon) ** 0.5

    # --------------------------------------------------------- Setup actions
    def _save_shift_now(self):
        if self.pages.currentIndex() == 2:
            self._flush_install_form()
        self._persist_shift(f"Saved profile '{self.state.profile}'.", quiet=False)

    def _save_profile_as(self):
        name = self.txt_profile.text().strip().upper() or "DEFAULT"
        if name == self.state.profile:
            self._save_shift_now()
            return
        path = os.path.join(DATA_DIR, f"tds_backup_{name}.json")
        if os.path.isfile(path):
            if QMessageBox.question(
                self, "Overwrite profile",
                f"Profile '{name}' already exists.\n\nOverwrite with your current shift?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            ) != QMessageBox.Yes:
                return
        if self.pages.currentIndex() == 2:
            self._flush_install_form()
        self._persist_shift(quiet=True)
        data = self.state.to_dict()
        data["profile"] = name
        import persistence as _persist
        if not _persist.save_state(data, path, DATA_DIR):
            self._warn("Could not write profile file.")
            return
        self._switch_profile(name, from_save_as=True)

    def _switch_profile(self, name: str | None = None, *, from_save_as: bool = False):
        if self.pages.currentIndex() == 2:
            self._flush_install_form()
        outgoing = self.state.profile
        self._persist_shift(quiet=True)
        name = (name or self.txt_profile.text().strip().upper() or "DEFAULT")
        self.txt_profile.setText(name)
        self._gps_follow = False
        self.nav = {"active": False}
        self._undo_stack.clear()
        self._export_nudge_shown = False
        self.state = RouteState(DATA_DIR, profile=name)
        self.state.load()
        self._sync_field_mode()
        if self.state.default_home:
            self.state.apply_default_home()
        self.excel_paths = [p for p in self.state.excel_paths if os.path.isfile(p)]
        self.est_paths = [p for p in self.state.est_paths if os.path.isfile(p)]
        self.state.excel_paths = list(self.excel_paths)
        self.state.est_paths = list(self.est_paths)
        self.current_index = min(self.state.current_index, max(0, len(self.state.stops) - 1))
        self.pickup_index = min(self.state.pickup_index, max(0, len(self._installed_stops()) - 1))
        self.spin_lat.setValue(self.state.home[0])
        self.spin_lon.setValue(self.state.home[1])
        self._refresh_origin_label()
        self._refresh_workflow_strip()
        self._refresh_offline_ui()
        self._refresh_file_lists()
        self._refresh_day_filter()
        self._warn_missing_upload_paths()
        self._update_right(force_map=bool(self.state.stops))
        if self.state.stops:
            self._refresh_route_list()
            if self.pages.currentIndex() == 2:
                self._refresh_install()
        self._push_state(fit=bool(self.state.stops))
        self._sync_prefs_ui()
        self._refresh_undo_ui()
        self._refresh_field_ready()
        msg = f"Profile '{name}' loaded."
        if from_save_as:
            msg = f"Saved and switched to profile '{name}'."
        elif outgoing != name:
            msg = f"Switched {outgoing} → {name}."
        self._info(msg)

    def _refresh_origin_label(self):
        dh = ""
        if self.state.default_home:
            dh = f"\nDefault saved: {self.state.default_home[0]:.5f}, {self.state.default_home[1]:.5f}"
        self.lbl_origin.setText(f"Origin: {self.state.home[0]:.5f}, {self.state.home[1]:.5f}{dh}")

    def _save_default_home(self):
        lat, lon = geo.normalize_ca_coords(self.spin_lat.value(), self.spin_lon.value())
        label = self.txt_address.text().strip() or f"{lat:.5f}, {lon:.5f}"
        self._commit_home_start(lat, lon, label, note=f"Default start saved:\n{label[:120]}")

    def _load_default_home(self):
        if not self.state.default_home:
            self._warn(
                "No saved start yet.\n\n"
                "Type your address and tap Search, then pick a match.")
            return
        self.state.apply_default_home()
        lat, lon = self.state.home
        label = self.state.saved_home_label or f"{lat:.5f}, {lon:.5f}"
        self._apply_home_ui(lat, lon, f"Loaded saved start:\n{label[:120]}")
        self.statusBar().showMessage(f"Start point loaded — {label[:60]}", 8000)

    def _evaluate_setup_checklist(self) -> dict:
        r = getattr(self, "_field_report", None)
        if r is None:
            r = check_all(APP_DIR, probe_gps=False, stop_server_after=False)
        return setup_checklist_eval(
            home=tuple(self.state.home),
            default_home=self.state.default_home,
            excel_paths=self.excel_paths,
            est_paths=self.est_paths,
            has_graph=road_router.has_graph(DATA_DIR),
            route_miles=float(self.state.route.get("miles", 0) or 0),
            field_report=r,
        )

    def _show_setup_checklist(self):
        ck = self._evaluate_setup_checklist()
        lines = []
        for it in ck["items"]:
            sym = "✓" if it["ok"] else "✗"
            extra = ""
            if it.get("detail"):
                extra = f" — {it['detail']}"
            lines.append(f"{sym} {it['label']}{extra}")
        title = "Ready to leave" if ck["ok"] else "Setup incomplete"
        QMessageBox.information(self, title, "\n".join(lines))

    def _run_setup_network_test(self):
        if self.state.offline_mode:
            self._field_notice("Tap I'm online in the top bar to test home Wi‑Fi.")
            return
        self.statusBar().showMessage("Testing home Wi‑Fi…", 3000)
        rows = setup_network.run_checks(data_dir=DATA_DIR, app_dir=APP_DIR)
        lines = []
        fails = 0
        for row in rows:
            sym = "OK" if row["ok"] else "FAIL"
            if not row["ok"]:
                fails += 1
            lines.append(f"[{sym}] {row['label']}: {row['detail']}")
        QMessageBox.information(
            self, "Home Wi‑Fi test",
            "\n".join(lines) + ("\n\nAll checks passed." if fails == 0 else f"\n\n{fails} issue(s) — fix before leaving."),
        )

    def _use_saved_home(self):
        if not self.state.saved_home_coords:
            self._warn(
                "No saved home yet.\n\n"
                "Type your address and tap Search, then pick a match — or use Save as my start.")
            return
        lat, lon = self.state.saved_home_coords
        label = self.state.saved_home_label or f"{lat:.5f}, {lon:.5f}"
        self._commit_home_start(lat, lon, label, note=f"Restored home:\n{label[:120]}")

    def _recover_map(self):
        self.bridge.refresh_view()
        self._push_state(fit=bool(self.state.stops))
        self.statusBar().showMessage("Map refreshed.", 5000)

    def _refresh_route_summary_ui(self):
        if not hasattr(self, "lbl_route_summary"):
            return
        if not self.state.stops:
            self.lbl_route_summary.setText("")
            return
        summ = build_route_summary(self.state.stops, self.state.route)
        from ui.simple_mode import COMPACT_UI
        if COMPACT_UI:
            miles = float(self.state.route.get("miles", 0.0) or 0)
            on_graph = bool(self.state.route.get("graph"))
            kind = "roads" if on_graph else "segments"
            self.lbl_route_summary.setText(
                f"{len(self.state.stops)} stops · {miles:.1f} mi · {kind} · {summ['text']}")
        else:
            self.lbl_route_summary.setText(summ["text"])

    def _next_stop_distance_mi(self) -> str:
        if not self.state.stops:
            return ""
        remaining = [
            s for s in self.state.stops
            if not s.get("installed") and not s.get("skipped")
        ]
        if not remaining:
            return " · all stops done"
        target = remaining[0]
        g = self.gps.latest() if hasattr(self, "gps") else {}
        if g.get("fix") and g.get("lat") is not None:
            d = self._dist_m(g["lat"], g["lon"], *self.state.point(target)) / 1609.34
            return f" · next Site {target.get('id', '?')} {d:.1f} mi"
        tlat, tlon = self.state.point(target)
        d = self._dist_m(self.state.home[0], self.state.home[1], tlat, tlon) / 1609.34
        return f" · next Site {target.get('id', '?')} ~{d:.1f} mi from start"

    def _maybe_refresh_field_strip(self) -> None:
        """Throttle status strip updates while driving (GPS ticks ~7 Hz)."""
        import time as _time
        if self._gps_follow:
            now = _time.time()
            if now - self._strip_tick < self._strip_throttle_s:
                return
            self._strip_tick = now
        self._refresh_field_strip_ui()

    def _refresh_field_alerts(self) -> None:
        text = field_alerts.pickup_reminder_text(self.state.stops)
        for attr in ("lbl_pickup_reminder", "lbl_download_reminder"):
            lbl = getattr(self, attr, None)
            if lbl is None:
                continue
            if text:
                lbl.setText(text)
                lbl.show()
            else:
                lbl.setText("")
                lbl.hide()

    def _counter_auto_connect(self) -> None:
        """One-shot connect when opening Install — skips if already live."""
        if self.pages.currentIndex() != 2:
            return
        if self._counter_connected:
            return
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        if not self._counter_selected_port():
            return
        self._counter_refresh_and_connect()

    def _maybe_export_nudge(self) -> None:
        if self._export_nudge_shown or not field_alerts.shift_closed(self.state.stops):
            return
        self._export_nudge_shown = True
        total = len(self.state.stops)
        dl = field_alerts.pending_download_count(self.state.stops)
        body = f"All {total} stops are installed or skipped."
        if dl:
            body += f"\n\n{dl} counter download(s) still pending — use Pickup tab."
        body += "\n\nExport Excel report now?"
        box = QMessageBox(self)
        box.setWindowTitle("Shift complete")
        box.setText(body)
        btn_go = box.addButton("Export Excel", QMessageBox.AcceptRole)
        box.addButton("Later", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() == btn_go:
            self._export_excel_quick()
            self._go_page(4)

    def _refresh_field_strip_ui(self):
        if not hasattr(self, "lbl_field_strip"):
            return
        gps = self.gps.latest() if hasattr(self, "gps") else {}
        if gps.get("fix"):
            gps_txt = f"GPS fix · {gps.get('satellites', 0)} sats"
        elif gps.get("connected"):
            gps_txt = "GPS searching…"
        else:
            gps_txt = "GPS not detected"
        next_txt = self._next_stop_distance_mi() if self.state.stops else ""
        self.lbl_field_strip.setText(f"{gps_txt}{next_txt}")
        if hasattr(self, "btn_saved_home"):
            has = bool(self.state.saved_home_coords)
            self.btn_saved_home.setEnabled(has)
            if has:
                short = self.state.saved_home_label[:50]
                if len(self.state.saved_home_label) > 50:
                    short += "…"
                self.btn_saved_home.setText(f"Use last address ({short})")
            else:
                self.btn_saved_home.setText("Use last address")
        if hasattr(self, "btn_use_default"):
            self.btn_use_default.setEnabled(bool(self.state.default_home))

    def _ready_offline(self):
        if self.state.offline_mode:
            self._info("Already in field (offline) mode. All data saves locally on the road.")
            return
        ck = self._evaluate_setup_checklist()
        if not ck["ok"]:
            body = "\n".join(f"• {b}" for b in ck["blockers"])
            self._warn(
                f"Cannot go offline yet:\n\n{body}\n\n"
                "Open Setup → Setup checklist for the full list.")
            return
        r = getattr(self, "_field_report", None) or check_all(APP_DIR, probe_gps=False, stop_server_after=False)
        gate = offline_gate_eval(
            r,
            has_stops=bool(self.state.stops),
            route_miles=float(self.state.route.get("miles", 0) or 0),
            graph_loaded=road_router.has_graph(DATA_DIR),
        )
        if gate["blockers"]:
            body = "\n".join(f"• {b}" for b in gate["blockers"])
            self._warn(f"Cannot go offline yet:\n\n{body}\n\nFix items on Setup → Field Readiness.")
            return
        if gate["warns"]:
            body = "\n".join(f"• {w}" for w in gate["warns"])
            if QMessageBox.question(
                self, "Ready for offline?",
                f"Warnings:\n\n{body}\n\nContinue to offline mode anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            ) != QMessageBox.Yes:
                return
        self.state.offline_mode = True
        self.state.save()
        self._sync_field_mode()
        self._refresh_offline_ui()
        self._apply_field_nav_shell()
        self._sync_map_health_interval()
        if self.pages.currentIndex() == 0:
            self._go_page(1)
        self._refresh_workflow_strip()
        self.statusBar().showMessage(
            "Field mode — on the road the app uses only local data (no internet).", 12000)
        self._info(
            "Ready for the road (offline mode).\n\n"
            "On site:\n"
            "• GPS, map, driving, installs, export — all local\n"
            "• No address search or road downloads (saves data)\n\n"
            "Back home on Wi‑Fi:\n"
            "• Tap I'm online in the top bar to set up the next day"
        )

    def _on_mode_online(self):
        if not self.state.offline_mode:
            self.statusBar().showMessage("Already online — home setup (Wi‑Fi tools enabled).", 5000)
            self._refresh_mode_bar()
            return
        self._resume_online()

    def _on_mode_offline(self):
        if self.state.offline_mode:
            self.statusBar().showMessage("Already offline — field mode (local data only).", 5000)
            self._refresh_mode_bar()
            return
        self._ready_offline()

    def _resume_online(self):
        if QMessageBox.question(
            self, "Back to home setup (online)",
            "Use Wi‑Fi at home again?\n\n"
            "• Address search and road map download work\n"
            "• Import road map from file still works anytime\n\n"
            "Your route and install progress stay saved.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self.state.offline_mode = False
        self.state.save()
        self._sync_field_mode()
        self._refresh_offline_ui()
        self._apply_field_nav_shell()
        self._sync_map_health_interval()
        self._refresh_address_hint()
        self._refresh_workflow_strip()
        self._refresh_online_status()
        self.statusBar().showMessage(
            "Home setup (online) — use Wi‑Fi for address, road map, and BUILD.", 10000)

    def _refresh_mode_bar(self):
        """Top bar: one place for online/offline mode (no duplicate status strings)."""
        if not hasattr(self, "btn_mode_online"):
            return
        on = self.state.offline_mode
        self.lbl_mode_pill.setText("OFFLINE" if on else "ONLINE")
        self.lbl_mode_pill.setProperty("mode", "offline" if on else "online")
        self.lbl_mode_pill.style().unpolish(self.lbl_mode_pill)
        self.lbl_mode_pill.style().polish(self.lbl_mode_pill)
        self.btn_mode_online.setChecked(not on)
        self.btn_mode_offline.setChecked(on)
        sub = "field mode · local only" if on else "home setup · Wi‑Fi tools on"
        if hasattr(self, "brand_sub"):
            self.brand_sub.setText(f"v{APP_VERSION}  ·  {sub}")

    def _refresh_offline_ui(self):
        self._sync_field_mode()
        on = self.state.offline_mode
        self._refresh_mode_bar()
        if on:
            self.lbl_offline.setText(
                "On the road — field mode. GPS, map, route, and installs use only local data.")
            self.lbl_offline.setStyleSheet("color:#138a3e;font-weight:700;")
        else:
            self.lbl_offline.setText(
                "At home: search address, download road map, BUILD ROUTE, then Go offline before you leave.")
            self.lbl_offline.setStyleSheet("color:#475569;font-size:12px;")
        allow = self._internet_allowed()
        self.txt_address.setEnabled(allow)
        if hasattr(self, "btn_address"):
            self.btn_address.setEnabled(allow)
        if hasattr(self, "btn_download_roads"):
            self.btn_download_roads.setEnabled(allow)
        if hasattr(self, "btn_import_roads"):
            self.btn_import_roads.setEnabled(True)
        self._refresh_address_hint()
        self._refresh_field_strip_ui()
        self._apply_field_nav_shell()
        self._sync_map_health_interval()

    def _refresh_online_status(self):
        """Geocode reachability hint when online (does not overwrite route status bar)."""
        if not self._internet_allowed():
            return
        self._retry_pending_field_geocode()
        reachable = connectivity.geocode_hosts_reachable()
        if reachable is False and hasattr(self, "lbl_address_hint"):
            self.lbl_address_hint.setText(
                "Wi‑Fi connected but geocoding sites look blocked — try hotspot, "
                "or use USB GPS / lat·lon.")
            self.lbl_address_hint.setStyleSheet("color:#b45309;font-weight:700;font-size:12px;")

    def _refresh_address_hint(self):
        if not hasattr(self, "lbl_address_hint"):
            return
        if self.state.offline_mode:
            self.lbl_address_hint.setText(
                "Field mode — address search off on the road. USB GPS or coordinates; "
                "tap I'm online when back home.")
            self.lbl_address_hint.setStyleSheet("color:#b45309;font-weight:700;font-size:12px;")
            return
        if not geo.geocode_available():
            self.lbl_address_hint.setText(
                f"Address search unavailable — {LAUNCH_HINT} (needs requests package).")
            self.lbl_address_hint.setStyleSheet("color:#b91c1c;font-weight:700;font-size:12px;")
            return
        self.lbl_address_hint.setText(
            "At home: type address + Search (5–20 sec). Internet used until you tap Go offline.")
        self.lbl_address_hint.setStyleSheet("")
        self._refresh_online_status()

    def _field_notice(self, msg: str, *, status_ms: int = 10000):
        """On the road: status bar only — no blocking dialogs for non-critical issues."""
        self.statusBar().showMessage(msg, status_ms)

    def _schedule_autosave(self):
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return
        self._autosave_timer.start(800)

    def _flush_install_form(self):
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return
        s = self.state.stops[self.current_index]
        s["street"] = self.txt_street.text().strip()
        s["direction"] = self.combo_dir.currentText()
        s["lanes"] = int(self.spin_lanes.value())
        s["serial"] = self.txt_serial.text().strip()
        s["notes"] = self.txt_notes.toPlainText()
        self._sync_counter_fields(s)

    def _sync_counter_fields(self, s: dict) -> None:
        """Keep stop + Excel export aligned with PicoCount serial and Unit ID."""
        sn = self.txt_serial.text().strip() if hasattr(self, "txt_serial") else ""
        if not sn:
            sn = str(s.get("counter_serial") or "").strip()
        if sn:
            s["counter_serial"] = sn
            s["serial"] = sn

    def _set_counter_connected_ui(self, connected: bool) -> None:
        self._counter_connected = connected
        apply_counter_panel_connected(getattr(self, "counter_panel", None), connected)
        if hasattr(self, "lbl_counter_connected"):
            if connected:
                self.lbl_counter_connected.show()
            else:
                self.lbl_counter_connected.hide()

    def _persist_shift(self, note: str = "", quiet: bool = False):
        self.state.current_index = self.current_index
        self.state.pickup_index = self.pickup_index
        if hasattr(self, "combo_day"):
            self.state.map_day_filter = self.combo_day.currentText()
        self.state.excel_paths = list(self.excel_paths)
        self.state.est_paths = list(self.est_paths)
        if self.state.save():
            if note and not quiet:
                self.statusBar().showMessage(note, 3000)
            elif not quiet:
                self.statusBar().showMessage("Shift saved on this laptop.", 2500)

    def _periodic_save_shift(self):
        if self.pages.currentIndex() == 2:
            self._flush_install_form()
        self._persist_shift(quiet=True)

    def _map_health_check(self):
        if self.right_stack.currentIndex() != 1 or not self.state.stops:
            return

        def cb(healthy):
            try:
                if healthy:
                    return
                self.bridge.refresh_view()
                self._push_state(fit=False)
                self.statusBar().showMessage("Map refreshed (recovered blank canvas).", 5000)
            except Exception:
                pass

        n = len(self._stops_for_map())
        self.view.page().runJavaScript(
            f"!!window.__mapLoaded && window.__dbg.lastStops >= {n} && window.__dbg.applied > 0",
            cb)

    def _autosave_current_stop(self):
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return
        self._flush_install_form()
        self._persist_shift("Saved locally.", quiet=False)

    def _apply_home_ui(self, lat: float, lon: float, note: str = "") -> None:
        lat, lon = geo.normalize_ca_coords(lat, lon)
        self.spin_lat.setValue(lat)
        self.spin_lon.setValue(lon)
        self._refresh_origin_label()
        self._refresh_workflow_strip()
        self._refresh_field_strip_ui()
        self._refresh_field_ready()
        self.bridge.fly_to(lat, lon, 13)
        self._push_state()
        if note:
            self._info(note)

    def _commit_home_start(self, lat: float, lon: float, label: str, *, note: str = "") -> bool:
        lat, lon = geo.normalize_ca_coords(lat, lon)
        if RouteState.is_factory_home(lat, lon):
            self._warn(
                "Those coordinates are still the factory demo location.\n\n"
                "Type your address and tap Search, use USB GPS, or enter your real lat/lon.")
            return False
        ok = self.state.set_start_point(lat, lon, label)
        if not ok:
            self._warn(
                "Could not write home to disk.\n\n"
                f"Check that {DATA_DIR} is writable (not read-only or full).")
            return False
        self.state.home = (lat, lon)
        msg = note or f"Home saved:\n{(label or f'{lat:.5f}, {lon:.5f}')[:120]}"
        self.statusBar().showMessage(
            f"Start point saved — {label[:60] if label else f'{lat:.5f}, {lon:.5f}'}",
            12000,
        )
        self._apply_home_ui(lat, lon, msg)
        return True

    def _set_origin(self, lat, lon, note=""):
        lat, lon = geo.normalize_ca_coords(lat, lon)
        self.state.home = (float(lat), float(lon))
        if not self.state.save():
            self._warn(
                "Could not save start point to disk.\n\n"
                f"Check that {DATA_DIR} is writable.")
        self._apply_home_ui(lat, lon, note)

    def _refresh_ports(self):
        self.combo_port.clear()
        self.combo_port.addItem("Auto-detect", None)
        for p in gps_reader.describe_ports():
            self.combo_port.addItem(f"{p['device']} - {p['description']}", p["device"])

    def _set_gps_port(self):
        dev = self.combo_port.currentData()
        try:
            self.gps.stop()
        except Exception:
            pass
        self.gps = gps_reader.GPSStream(preferred_port=dev)
        self.gps.start()
        self.statusBar().showMessage(f"GPS port set to {dev or 'Auto-detect'}", 4000)

    def _origin_from_gps(self):
        g = self.gps.latest()
        fix = gps_reader.fix_from_snapshot(g)
        if fix is not None:
            label = f"USB GPS {fix[0]:.5f}, {fix[1]:.5f}"
            self._commit_home_start(fix[0], fix[1], label, note="Origin set from USB GPS.")
            return
        self._warn(gps_reader.no_fix_message(g))

    def _origin_from_address(self):
        if not self._internet_allowed():
            self._field_notice(
                "Field mode — address search is off. Use GPS or coordinates; "
                "Tap I'm online at home for address search.")
            return
        if not geo.geocode_available():
            self._warn(
                "Address search needs the 'requests' library.\n\n"
                f"Launch with {LAUNCH_HINT} so dependencies are active.")
            return
        addr = self.txt_address.text().strip()
        if not addr:
            self.statusBar().showMessage("Type an address first.", 3000)
            return
        if getattr(self, "_geocode_thread", None) and self._geocode_thread.isRunning():
            self.statusBar().showMessage("Address search already running…", 3000)
            return

        dlg = QProgressDialog("Searching address online…\n\nThis can take 5–20 seconds.", None, 0, 0, self)
        dlg.setWindowTitle("Address search")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setMinimumWidth(380)
        self.btn_address.setEnabled(False)
        self.txt_address.setEnabled(False)

        thread = GeocodeThread(addr, limit=6)
        self._geocode_thread = thread

        def _restore_addr_ui():
            dlg.close()
            allow = self._internet_allowed()
            self.btn_address.setEnabled(allow)
            self.txt_address.setEnabled(allow)
            self._geocode_thread = None

        def done(cands: list, err: str):
            _restore_addr_ui()
            if err == "missing_requests":
                self._warn(f"Address search unavailable — {LAUNCH_HINT}.")
                return
            if err:
                self._warn(f"Address search failed:\n\n{err}")
                return
            if not cands:
                self._warn(
                    "Address not found.\n\n"
                    "Try:\n"
                    "• Full street + city + CA zip\n"
                    "  (e.g. 123 Main St, Garden Grove, CA 92840)\n"
                    "• Phone hotspot if work Wi‑Fi blocks geocoding sites\n"
                    "• Read USB GPS, or enter lat/lon → Save coordinates\n\n"
                    "Run: scripts\\diagnose_network.py (now includes address hosts)"
                )
                return
            self._pick_geocode_candidate(cands)

        thread.finished_result.connect(done)
        thread.start()
        dlg.show()

    def _pick_geocode_candidate(self, cands: list[dict]):
        from PySide6.QtWidgets import QInputDialog

        if len(cands) == 1:
            c = cands[0]
            self._commit_home_start(
                c["lat"], c["lon"], c["label"],
                note=f"Home saved:\n{c['label'][:120]}")
            return
        labels = [c["label"][:120] for c in cands]
        pick, ok = QInputDialog.getItem(
            self, "Pick your address", "Several matches — choose one:", labels, 0, False)
        if not ok or not pick:
            self.statusBar().showMessage("Address search cancelled.", 4000)
            return
        idx = labels.index(pick)
        c = cands[idx]
        self._commit_home_start(
            c["lat"], c["lon"], c["label"],
            note=f"Home saved:\n{c['label'][:120]}")

    def _origin_from_coords(self):
        lat, lon = self.spin_lat.value(), self.spin_lon.value()
        label = self.txt_address.text().strip() or f"{lat:.5f}, {lon:.5f}"
        if self._commit_home_start(lat, lon, label):
            self._refresh_map_preview()

    def _sync_upload_paths(self):
        self.state.excel_paths = list(self.excel_paths)
        self.state.est_paths = list(self.est_paths)
        self.state.save()

    @staticmethod
    def _stop_worker(thread: QThread | None, wait_ms: int = 4000):
        if thread is None or not thread.isRunning():
            return
        thread.requestInterruption()
        if not thread.wait(wait_ms):
            thread.terminate()
            thread.wait(2000)

    def _pick_excel(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Excel/CSV", "",
                                                "Spreadsheets (*.xlsx *.xls *.csv);;All files (*)")
        for p in paths:
            if p not in self.excel_paths:
                self.excel_paths.append(p)
        self._refresh_file_lists()
        self._sync_upload_paths()
        self._refresh_map_preview()

    def _pick_est(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add .EST maps", "",
                                                "EST maps (*.est *.EST);;All files (*)")
        for p in paths:
            if p not in self.est_paths:
                self.est_paths.append(p)
        self._refresh_file_lists()
        self._sync_upload_paths()
        self._refresh_map_preview()

    def _clear_files(self):
        if QMessageBox.question(
            self, "Clear file lists",
            "Remove Excel and .EST paths from this profile only?\n\n"
            "Your route, installs, and pickup progress are NOT cleared.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self.excel_paths = []
        self.est_paths = []
        self._refresh_file_lists()
        self._sync_upload_paths()
        self._refresh_map_preview()
        self.statusBar().showMessage("File lists cleared — shift data unchanged.", 5000)

    def _load_demo_files(self):
        if not os.path.isfile(DEMO_CSV) or not os.path.isfile(DEMO_EST):
            self._warn("Demo files missing from demo_data/ folder.")
            return
        added = False
        if DEMO_CSV not in self.excel_paths:
            self.excel_paths.append(DEMO_CSV)
            added = True
        if DEMO_EST not in self.est_paths:
            self.est_paths.append(DEMO_EST)
            added = True
        self._refresh_file_lists()
        self._sync_upload_paths()
        self._refresh_map_preview()
        msg = "Demo files loaded (5 sites)." if added else "Demo files already in the list."
        self.statusBar().showMessage(
            f"{msg} Blue/red dots = begin/end of each line. BUILD ROUTE when ready.", 8000)

    @staticmethod
    def _est_label_from_path(path: str) -> str:
        """Use upload filename (no extension) so Day# matches the file."""
        return os.path.splitext(os.path.basename(path))[0]

    def _refresh_file_lists(self):
        self.list_excel.clear()
        self.list_excel.addItems([os.path.basename(p) for p in self.excel_paths])
        self.list_est.clear()
        for p in self.est_paths:
            item = QListWidgetItem(self._est_label_from_path(p))
            item.setToolTip(p)
            self.list_est.addItem(item)
        self._refresh_workflow_strip()

    def _est_configs(self) -> list[dict]:
        return [{"path": p, "label": self._est_label_from_path(p)} for p in self.est_paths]

    def _gather_area_points(self):
        """All segment endpoints + home so the road download bbox covers every street line."""
        pts = [list(self.state.home)]
        if self.state.stops:
            for s in self.state.stops:
                pts.append([s["begin_lat"], s["begin_lon"]])
                pts.append([s["end_lat"], s["end_lon"]])
            return pts
        sites = ingest.parse_excel_sites(self.excel_paths)
        stops = ingest.match_est_files(self._est_configs(), sites, self.state.home)
        for s in stops:
            pts.append([s["begin_lat"], s["begin_lon"]])
            pts.append([s["end_lat"], s["end_lon"]])
        return pts

    def _download_basemap(self):
        from core.map_setup import basemap_ok

        if not self._internet_allowed():
            self.statusBar().showMessage(
                "Go online (top bar) to download the California map.", 8000)
            return
        if basemap_ok(DATA_DIR):
            self.statusBar().showMessage("California map already installed.", 6000)
            return
        dlg = QProgressDialog(
            "Downloading California map (~10-20 min on Wi-Fi)...",
            "Cancel", 0, 0, self)
        dlg.setWindowTitle("California map")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setMinimumWidth(420)
        thread = MapSetupThread()
        self._map_setup_thread = thread

        def done(res: dict):
            dlg.close()
            if res.get("ok"):
                self._refresh_field_ready()
                self._push_state(fit=True)
                self.statusBar().showMessage("California map ready.", 8000)
            else:
                self.statusBar().showMessage(
                    f"Map download failed: {res.get('error', 'unknown')}", 12000)

        thread.finished_result.connect(done)
        thread.start()
        dlg.show()

    def _download_roads(self):
        if not self._internet_allowed():
            self._warn(
                "Field (offline) mode — download needs Wi‑Fi at home.\n\n"
                "Use Import road map if you copied road_graph.graphml, or "
                "Tap I'm online on home Wi‑Fi.")
            return
        if not road_router.HAS_ROUTING:
            self.statusBar().showMessage(
                "Road download skipped — import road_graph.graphml or keep going without it.",
                8000)
            return
        if road_router.has_graph(DATA_DIR):
            if QMessageBox.question(
                self, "Road map",
                "A road map is already saved for this area.\n\nRe-download from the internet anyway?",
            ) != QMessageBox.Yes:
                self.statusBar().showMessage("Using existing local road map.", 5000)
                return
        pts = self._gather_area_points()
        if len(pts) < 2:
            self._warn("Add your Excel + .EST files first so I know the area.")
            return
        try:
            _w, _s, _e, _n, span_mi = road_router.bbox_for_points(pts)
        except ValueError as exc:
            self._warn(str(exc))
            return
        net_err = road_router.probe_roads_internet()
        if net_err:
            self.statusBar().showMessage(
                "Road servers look blocked — trying download anyway (use hotspot if this fails)...",
                12000,
            )

        dlg = QProgressDialog("Downloading road map (needs internet)...", "Cancel", 0, 0, self)
        dlg.setWindowTitle("Downloading")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setMinimumWidth(400)

        import time as _time
        t0 = _time.time()
        etimer = QTimer(self)

        thread = DownloadRoadsThread(pts, DATA_DIR)
        self._dl_thread = thread

        def tick():
            dlg.setLabelText(
                f"Downloading road map from OpenStreetMap...\n\n"
                f"Elapsed: {int(_time.time() - t0)}s  (~{span_mi:.0f} mi work area)\n\n"
                f"Usually 30-90 seconds on home Wi-Fi.\n"
                f"If this passes 3 minutes, work firewall may be blocking it — Cancel, "
                f"then copy tds_data\\road_graph.graphml from home.")

        def done(res):
            etimer.stop()
            dlg.close()
            self._dl_thread = None
            if res.get("ok"):
                named = res.get("named_edges", 0)
                self._info(
                    f"Road map ready: {res['nodes']} intersections (~{res['radius_mi']} mi span).\n"
                    f"Street names on {named} road segments (for driving directions).\n"
                    f"Now press {BUILD_LABEL}.")
                self.statusBar().showMessage(
                    "Road map downloaded — build your route next.", 8000)
                self._refresh_field_ready()
            else:
                err = res.get("error", "unknown")
                self._warn(
                    f"Road map download failed:\n\n{err}\n\n"
                    "On work Wi‑Fi: use phone hotspot and try again, OR\n"
                    "copy tds_data\\road_graph.graphml from your home PC and tap\n"
                    "Import road map from file.\n\n"
                    "Cmd download:\n"
                    "  .venv\\Scripts\\python.exe scripts\\download_road_map.py --demo"
                )

        def canceled():
            etimer.stop()
            self._stop_worker(thread)
            dlg.close()
            self._dl_thread = None

        etimer.timeout.connect(tick)
        etimer.start(1000)
        dlg.canceled.connect(canceled)
        thread.finished_result.connect(done)
        thread.start()
        dlg.show()
        tick()

    def _import_roads(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import road map",
            DATA_DIR,
            "Road graph (*.graphml);;All files (*)",
        )
        if not path:
            return
        try:
            info = road_router.import_graph(path, DATA_DIR)
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Could not import road map:\n\n{exc}")
            return
        nodes = info.get("nodes", 0)
        if nodes:
            self._info(
                f"Road map imported: {nodes:,} intersections.\n"
                f"Now press {BUILD_LABEL}.")
        elif road_router.has_graph(DATA_DIR):
            g = road_router.load_graph(DATA_DIR)
            n = len(g.nodes) if g else 0
            self._info(f"Road map imported and loaded ({n:,} nodes).\nNow press {BUILD_LABEL}.")
        else:
            mb = info.get("size_mb", "?")
            self._warn(
                f"File copied ({mb} MB) but graph did not load.\n\n"
                f"{LAUNCH_HINT} or re-copy road_graph.graphml from home PC."
            )
            return
        self.statusBar().showMessage("Road map imported from file.", 8000)
        self._refresh_field_ready()

    def _build_route_from_uploads(self):
        if not self.excel_paths or not self.est_paths:
            self._warn("Add at least one Excel/CSV and one .EST map first.")
            return
        try:
            sites = ingest.parse_excel_sites(self.excel_paths)
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Could not read Excel/CSV: {exc}")
            return
        if not sites:
            self._warn("No site coordinates found in the Excel/CSV (need begin lat/lon columns).")
            return
        cfgs = self._est_configs()
        stops = ingest.match_est_files(cfgs, sites, self.state.home)
        if not stops:
            self._warn("0 sites matched. Check that site IDs appear in the .EST files.")
            return

        report = validate.validate_build(
            self.excel_paths, cfgs, sites, stops,
            home=tuple(self.state.home),
            default_home=self.state.default_home,
        )
        if not report["ok"]:
            self._warn("Cannot build route:\n\n" + "\n".join(report["errors"]))
            return
        if report["warnings"]:
            body = "\n".join(report["warnings"])
            if QMessageBox.question(
                self, "Review before build",
                f"{body}\n\nBuild route anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            ) != QMessageBox.Yes:
                return

        self.state.active_files = [c["label"] for c in cfgs]

        old_by_uid = {s["uid"]: s for s in self.state.stops}
        merged = [ingest.merge_stop_progress(old_by_uid.get(f["uid"]), f) for f in stops]
        kept = sum(1 for f in merged if f["uid"] in old_by_uid
                   and (old_by_uid[f["uid"]].get("installed") or old_by_uid[f["uid"]].get("skipped")))
        if kept:
            self.statusBar().showMessage(
                f"Re-build: kept install/pickup data on {kept} site(s).", 6000)

        self.state.stops = merged
        self._map_preview_stops = []
        self.state.route = {"polyline": [], "miles": 0.0, "graph": False}
        self._persist_shift(quiet=True)
        self.current_index = min(self.current_index, max(0, len(self.state.stops) - 1))
        self._update_right(force_map=True)
        self._go_page(1)
        self._refresh_route_list()
        self._refresh_day_filter()
        self._push_state(fit=True)
        mode = self._ask_route_build_mode()
        if mode == "pick":
            self._begin_route_pick(merged)
        elif mode == "optimize":
            self._optimize_and_route(merged)
        else:
            self.statusBar().showMessage("Route build cancelled.", 4000)

    @staticmethod
    def _street_label(s: dict) -> str:
        st = str(s.get("street", "")).strip()
        if not st or st.lower() in ("nan", "none", "nat"):
            return f"Site {s.get('id', '')}"
        return st

    def _ensure_route_pick_dialog(self) -> RoutePickOrderDialog:
        if self._route_pick_dialog is None:
            dlg = RoutePickOrderDialog(self)
            dlg.order_changed.connect(self._route_pick_set_order)
            dlg.apply_requested.connect(self._route_pick_apply)
            self._route_pick_dialog = dlg
        return self._route_pick_dialog

    def _enter_pick_map_focus(self) -> None:
        """Give the map most of the window — pick is click-driven, not sidebar forms."""
        if not self._pick_layout_active:
            self._pick_splitter_saved = list(self._splitter.sizes())
            self._pick_layout_active = True
        total = max(800, sum(self._splitter.sizes()))
        self._splitter.setSizes([220, max(500, total - 220)])

    def _exit_pick_map_focus(self) -> None:
        if self._pick_layout_active and self._pick_splitter_saved:
            self._splitter.setSizes(self._pick_splitter_saved)
        self._pick_layout_active = False
        self._pick_splitter_saved = None

    def _show_route_pick_dialog(self) -> None:
        dlg = self._ensure_route_pick_dialog()
        if not dlg.isVisible():
            dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        if self.isVisible():
            margin = 20
            x = self.geometry().right() - dlg.width() - margin
            y = self.geometry().top() + 72
            dlg.move(max(margin, x), max(margin, y))

    def _hide_route_pick_dialog(self) -> None:
        if self._route_pick_dialog is not None:
            self._route_pick_dialog.hide()

    def _route_pick_set_order(self, uids: list[str]) -> None:
        if not self._route_pick_mode:
            return
        by_uid = {s["uid"]: s for s in self.state.stops}
        prev = set(self._route_pick_uids)
        nxt = set(uids)
        for uid in prev - nxt:
            self._route_pick_sides.pop(uid, None)
            s = by_uid.get(uid)
            if s:
                s.pop("pick_cross_locked", None)
                for key in ("cross_lat", "cross_lon", "cross_side"):
                    s.pop(key, None)
        self._route_pick_uids = [u for u in uids if u in by_uid]
        self._refresh_route_pick_ui(sync_dialog=False)
        self._refresh_route_list()
        self._push_state()

    def _begin_route_pick(self, stops: list[dict]) -> None:
        self._end_manual_grab(silent=True)
        from core.map_display import enrich_segment_paths

        self._route_pick_mode = True
        self._route_pick_uids = []
        self._route_pick_sides = {}
        self.state.stops = list(stops)
        self.state.route = {"polyline": [], "miles": 0.0, "graph": False}
        if self.chk_show_segments.isChecked():
            enrich_segment_paths(self.state.stops, DATA_DIR)
        self._go_page(1)
        self._enter_pick_map_focus()
        self._refresh_route_pick_ui()
        self._show_route_pick_dialog()
        self._refresh_route_list()
        self._push_state(fit=True)
        self.statusBar().showMessage(
            f"Pick route on map — {self._pick_prompt_text()}. "
            "Blue = begin, red = end. Order list is on the right.",
            12000)

    def _refresh_route_pick_ui(self, *, sync_dialog: bool = True) -> None:
        if not hasattr(self, "lbl_pick_status"):
            return
        n = len(self._route_pick_uids)
        total = len(self.state.stops)
        on = self._route_pick_mode
        if hasattr(self, "sec_pick") and self.sec_pick is not None and SIMPLE_MODE:
            self.sec_pick.setVisible(on)
        self.btn_pick_apply.setEnabled(on and n > 0 and n >= total)
        if hasattr(self, "btn_pick_auto"):
            self.btn_pick_auto.setEnabled(False)
            self.btn_pick_auto.hide()
        self.btn_pick_clear.setEnabled(on and n > 0)
        if hasattr(self, "btn_pick_order_win"):
            self.btn_pick_order_win.setEnabled(on)
            self.btn_pick_order_win.setVisible(not on)
        if hasattr(self, "pick_combo_row"):
            self.pick_combo_row.setVisible(not on)
        if on:
            self._enter_pick_map_focus()
        elif self._pick_layout_active:
            self._exit_pick_map_focus()
        self._refresh_pick_site_combo()
        if not on:
            self.lbl_pick_status.setStyleSheet("")
            self.lbl_pick_status.setText(
                "Route applied. Numbers on the map match drive order. "
                f"Re-plan with {BUILD_LABEL} on Setup.")
            if sync_dialog:
                self._hide_route_pick_dialog()
            return
        letters = self._pick_site_letters()
        self.lbl_pick_status.setStyleSheet(
            "font-size:14px;font-weight:700;color:#0d47a1;padding:8px 0;")
        if n >= total:
            self.lbl_pick_status.setText(
                f"All {total} stops picked on the map. Tap Apply route.")
        else:
            self.lbl_pick_status.setText(
                f"{self._pick_prompt_text()} — blue begin or red end. "
                f"Order updates in the popup.")
        if sync_dialog and on and self._route_pick_dialog is not None:
            by_uid = {s["uid"]: s for s in self.state.stops}
            self._route_pick_dialog.sync_from_parent(
                uids=list(self._route_pick_uids),
                stops_by_uid=by_uid,
                letters=letters,
                street_label=self._street_label,
                total=total,
                prompt=self._pick_prompt_text(),
                pick_sides=dict(self._route_pick_sides),
            )
            self._show_route_pick_dialog()

    def _refresh_pick_site_combo(self) -> None:
        if not hasattr(self, "combo_pick_site"):
            return
        n = len(self._route_pick_uids)
        total = len(self.state.stops)
        on = self._route_pick_mode
        self.combo_pick_site.blockSignals(True)
        self.combo_pick_site.clear()
        if not on:
            self.combo_pick_site.setEnabled(False)
            self.lbl_pick_slot.setText("Stop:")
            self.combo_pick_site.addItem("(not picking)")
            self.combo_pick_site.blockSignals(False)
            return
        letters = self._pick_site_letters()
        picked = set(self._route_pick_uids)
        if n >= total:
            self.lbl_pick_slot.setText("Done:")
            self.combo_pick_site.setEnabled(False)
            self.combo_pick_site.addItem("All stops assigned")
            self.combo_pick_site.blockSignals(False)
            return
        self.lbl_pick_slot.setText(f"Stop {n + 1}:")
        self.combo_pick_site.setEnabled(True)
        self.combo_pick_site.addItem("— choose site —", None)
        for s in self.state.stops:
            if s["uid"] in picked:
                continue
            letter = letters.get(s["uid"], "?")
            label = f"[{letter}] Site {s['id']} — {self._street_label(s)}"
            self.combo_pick_site.addItem(label, s["uid"])
        self.combo_pick_site.setCurrentIndex(0)
        self.combo_pick_site.blockSignals(False)

    def _on_pick_combo_chosen(self, index: int) -> None:
        if not self._route_pick_mode or index <= 0:
            return
        uid = self.combo_pick_site.itemData(index)
        if uid:
            self._route_pick_add(str(uid))

    def _route_pick_add(self, uid: str, *, side: str | None = None) -> None:
        if not self._route_pick_mode:
            return
        if uid in self._route_pick_uids:
            self.statusBar().showMessage("Already in your route — pick the next site.", 4000)
            return
        by_uid = {s["uid"]: s for s in self.state.stops}
        stop = by_uid.get(uid)
        if stop and side in ("begin", "end"):
            self._route_pick_sides[uid] = side
            self._apply_pick_side(stop, side)
        self._route_pick_uids.append(uid)
        n = len(self._route_pick_uids)
        total = len(self.state.stops)
        self._refresh_route_pick_ui()
        self._refresh_route_list()
        self._push_state()
        side_note = ""
        if side in ("begin", "end"):
            side_note = f" ({side} end)"
        if n >= total:
            self.statusBar().showMessage(
                f"Stop {n}{side_note} added — all sites chosen. Tap Apply route.", 8000)
        else:
            self.statusBar().showMessage(
                f"Stop {n}{side_note} added — {self._pick_prompt_text()}.", 8000)

    def _route_pick_clear(self) -> None:
        if not self._route_pick_mode:
            return
        self._route_pick_uids = []
        self._route_pick_sides = {}
        for s in self.state.stops:
            s.pop("pick_cross_locked", None)
            for key in ("cross_lat", "cross_lon", "cross_side"):
                s.pop(key, None)
        self._refresh_route_pick_ui()
        self._refresh_route_list()
        self._push_state()
        self.statusBar().showMessage(
            f"Picks cleared — {self._pick_prompt_text()}.", 6000)

    def _route_pick_auto_finish(self) -> None:
        if not self._route_pick_mode or not self.state.stops:
            return
        from core.map_display import auto_finish_order

        by_uid = {s["uid"]: s for s in self.state.stops}
        picked = [by_uid[u] for u in self._route_pick_uids if u in by_uid]
        remaining = [s for s in self.state.stops if s["uid"] not in self._route_pick_uids]
        ordered = auto_finish_order(tuple(self.state.home), picked, remaining, DATA_DIR)
        self._route_pick_uids = [s["uid"] for s in ordered]
        self._refresh_route_pick_ui()
        self._refresh_route_list()
        self._push_state()
        self.statusBar().showMessage(
            f"Auto-finished — {len(self._route_pick_uids)} stops in order. Tap Apply route.", 8000)

    def _route_pick_apply(self) -> None:
        total = len(self.state.stops)
        if not self._route_pick_mode or not self._route_pick_uids:
            self._warn("Pick stop 1 on the map (blue or red dot) or from the dropdown.")
            return
        if len(self._route_pick_uids) < total:
            self._warn(
                f"Pick all {total} stops before Apply "
                f"({len(self._route_pick_uids)} chosen so far).")
            return
        if self._route_thread is not None and self._route_thread.isRunning():
            self.statusBar().showMessage("Route build already running…", 4000)
            return
        if not road_router.has_graph(DATA_DIR):
            msg = (
                "Download the road map first (Setup tab → Download road map).\n\n"
                "That is required for accurate routes that follow real streets.")
            if self.state.offline_mode:
                self._field_notice(
                    "No local road map — import road_graph.graphml at home, or resume online mode.")
            else:
                self._warn(msg)
            return

        import time as _time

        dlg = QProgressDialog(
            "Applying your route order on real streets…",
            "Cancel", 0, 0, self)
        dlg.setWindowTitle("Apply route")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setMinimumWidth(420)
        t0 = _time.time()

        thread = RouteApplyPickThread(
            tuple(self.state.home),
            list(self._route_pick_uids),
            list(self.state.stops),
            DATA_DIR,
            dict(self._route_pick_sides),
        )
        self._route_thread = thread
        self.btn_pick_apply.setEnabled(False)
        if self._route_pick_dialog is not None:
            self._route_pick_dialog.btn_apply.setEnabled(False)

        def on_progress(msg: str):
            dlg.setLabelText(f"{msg}\n\nElapsed: {int(_time.time() - t0)}s")

        def _restore_apply_btn():
            if self._route_pick_mode:
                n = len(self._route_pick_uids)
                total_st = len(self.state.stops)
                enabled = n > 0 and n >= total_st
                self.btn_pick_apply.setEnabled(enabled)
                if self._route_pick_dialog is not None:
                    self._route_pick_dialog.btn_apply.setEnabled(enabled)

        def done(res: dict):
            dlg.close()
            self._route_thread = None
            _restore_apply_btn()
            if not res.get("ok"):
                err = f"Apply route failed: {res.get('error', 'unknown')}"
                if self.state.offline_mode:
                    self._field_notice(err)
                else:
                    self._warn(err)
                if res.get("trace"):
                    print(res["trace"])
                return
            self.state.stops = res["order"]
            self.state.route = res["route"]
            self._route_pick_mode = False
            self._route_pick_uids = []
            self._route_pick_sides = {}
            self._exit_pick_map_focus()
            self._hide_route_pick_dialog()
            self._persist_shift(quiet=True)
            self._refresh_route_list()
            self._refresh_route_pick_ui()
            self._refresh_route_summary_ui()
            self._refresh_field_ready()
            self._push_state(fit=True)
            miles = res["route"].get("miles", 0.0)
            self.statusBar().showMessage(
                f"Route applied: {len(self.state.stops)} stops, {miles:.1f} mi "
                "(street-traced sites).",
                10000,
            )
            if hasattr(self, "btn_build"):
                self.btn_build.setEnabled(True)
                self.btn_build.setText(BUILD_LABEL)

        def canceled():
            self._stop_worker(thread)
            dlg.close()
            self._route_thread = None
            _restore_apply_btn()
            self.statusBar().showMessage("Apply route cancelled.", 4000)

        dlg.canceled.connect(canceled)
        thread.progress_text.connect(on_progress)
        thread.finished_result.connect(done)
        thread.start()
        dlg.show()
        on_progress("Starting…")

    def _highlight_stop_uid(self) -> str | None:
        if self._manual_grab_mode and self.state.stops and self.current_index < len(self.state.stops):
            uid = str(self.state.stops[self.current_index].get("uid") or "")
            return uid or None
        nxt = self._next_leg_payload()
        return nxt["to_uid"] if nxt else None

    def _optimize_and_route(self, stops):
        self._route_pick_mode = False
        self._route_pick_uids = []
        self._route_pick_sides = {}
        self._exit_pick_map_focus()
        self._hide_route_pick_dialog()
        if not road_router.has_graph(DATA_DIR):
            msg = (
                "Download the road map first (Setup tab → Download road map).\n\n"
                "That is required for accurate routes that follow real streets and "
                "cross each site line efficiently.")
            if self.state.offline_mode:
                self._field_notice(
                    "No local road map — import road_graph.graphml at home, or resume online mode.")
            else:
                self._warn(msg)
            return

        dlg = QProgressDialog(
            "Optimizing route on real streets\n(crossing each site line in best order)...",
            "Cancel", 0, 0, self)
        dlg.setWindowTitle("Building route")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setMinimumWidth(420)

        import time as _time
        t0 = _time.time()
        etimer = QTimer(self)
        if hasattr(self, "btn_build"):
            self.btn_build.setEnabled(False)
            self.btn_build.setText("BUILDING ROUTE…")
        thread = RouteOptimizeThread(list(stops), tuple(self.state.home), DATA_DIR)
        self._route_thread = thread

        def _restore_build_btn():
            if hasattr(self, "btn_build"):
                self.btn_build.setEnabled(True)
                self.btn_build.setText(BUILD_LABEL)

        def on_progress(msg: str):
            dlg.setLabelText(f"{msg}\n\nElapsed: {int(_time.time() - t0)}s")

        def tick():
            pass  # progress_text from worker updates the label

        def done(res):
            etimer.stop()
            dlg.close()
            self._route_thread = None
            _restore_build_btn()
            if not res.get("ok"):
                err = f"Routing failed: {res.get('error', 'unknown')}"
                if self.state.offline_mode:
                    self._field_notice(err)
                else:
                    self._warn(err)
                if res.get("trace"):
                    print(res["trace"])
                return
            self.state.stops = res["order"]
            self.state.route = res["route"]
            self.current_index = min(self.current_index, max(0, len(self.state.stops) - 1))
            self._persist_shift(quiet=True)
            self._refresh_route_list()
            self._refresh_day_filter()
            self._update_right(force_map=True)
            self._push_state(fit=True)
            miles = res["route"].get("miles", 0.0)
            r = res["route"]
            if r.get("graph"):
                kind = "traced on real streets"
                failed = int(r.get("failed_legs") or 0)
                if failed:
                    kind += f" ({failed} leg(s) need road map refresh)"
            else:
                kind = "straight-line only — download road map on Setup"
            self.statusBar().showMessage(
                f"Route ready: {len(res['order'])} stops, {miles:.1f} mi — {kind}", 12000)
            if not r.get("graph"):
                self._warn(
                    "Route line is straight (chord) because no road graph is loaded.\n\n"
                    "Setup → Download road map (or import road_graph.graphml), then BUILD again.")
            self._refresh_field_ready()
            self._refresh_route_summary_ui()

        def canceled():
            etimer.stop()
            self._stop_worker(thread)
            dlg.close()
            self._route_thread = None
            _restore_build_btn()

        etimer.timeout.connect(tick)
        dlg.canceled.connect(canceled)
        thread.progress_text.connect(on_progress)
        thread.finished_result.connect(done)
        thread.finished.connect(lambda: etimer.stop())
        thread.start()
        dlg.show()
        tick()

    def _show_setup_wizard(self):
        dlg = SetupWizard(self)
        dlg.exec()
        self._refresh_workflow_strip()
        self._refresh_field_ready()

    def _reoptimize(self):
        if not self.state.stops:
            return
        mode = self._ask_route_build_mode()
        if mode is None:
            return
        stops = self._stops_from_uploads_merged() or list(self.state.stops)
        if mode == "pick":
            self._begin_route_pick(stops)
        else:
            self._route_pick_mode = False
            self._route_pick_uids = []
            self._route_pick_sides = {}
            self._exit_pick_map_focus()
            self._hide_route_pick_dialog()
            self._optimize_and_route(stops)

    def _stops_from_uploads_merged(self) -> list[dict] | None:
        """Fresh site list from current Excel/EST (keeps field progress), not saved route order."""
        if not self.excel_paths or not self.est_paths:
            return None
        try:
            sites = ingest.parse_excel_sites(self.excel_paths)
            cfgs = self._est_configs()
            stops = ingest.match_est_files(cfgs, sites, self.state.home)
            if not stops:
                return None
            old_by_uid = {s["uid"]: s for s in self.state.stops}
            return [ingest.merge_stop_progress(old_by_uid.get(f["uid"]), f) for f in stops]
        except Exception:
            return None

    def _nudge_stop(self, delta: int):
        if not self.state.stops:
            return
        idx = self.list_route.currentRow()
        if idx < 0:
            idx = self.current_index
        j = idx + delta
        if j < 0 or j >= len(self.state.stops):
            return
        stops = list(self.state.stops)
        stops[idx], stops[j] = stops[j], stops[idx]
        self.state.stops = stops
        self.current_index = j
        self._retrace_route_only(select_row=j)

    def _retrace_route_only(self, *, select_row: int | None = None):
        if not self.state.stops:
            return
        from core import routing
        res = routing.retrace_only(
            list(self.state.stops), tuple(self.state.home), DATA_DIR)
        from core.map_display import enrich_segment_paths

        self.state.route = res["route"]
        if self.chk_show_segments.isChecked():
            enrich_segment_paths(self.state.stops, DATA_DIR)
        self._persist_shift(quiet=True)
        self._refresh_route_list()
        if select_row is not None:
            self.list_route.setCurrentRow(select_row)
        self._push_state()
        self.statusBar().showMessage(
            f"Route re-traced — {self.state.route.get('miles', 0):.1f} mi (order unchanged).",
            6000,
        )

    def _reset_route(self):
        if QMessageBox.question(
            self, "Clear shift data",
            "Clear stops, route, and install/pickup progress?\n\n"
            "Your Excel/EST file list stays — only you can wipe that via "
            "\"Clear file lists\" on Setup.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self._stop_drive()
        self._route_pick_mode = False
        self._route_pick_uids = []
        self._route_pick_sides = {}
        self._exit_pick_map_focus()
        self._hide_route_pick_dialog()
        self._undo_stack.clear()
        self._refresh_undo_ui()
        self.state.clear_shift(wipe_upload_paths=False)
        self.current_index = self.pickup_index = 0
        self._update_right()
        self._push_state(fit=True)
        self._refresh_route_list()
        self._refresh_workflow_strip()
        self.statusBar().showMessage("Shift cleared. Upload files are still listed on Setup.", 8000)

    # --------------------------------------------------------- Route list UI
    def _refresh_route_list(self):
        self.list_route.clear()
        letters = self._pick_site_letters() if self._route_pick_mode else {}
        if self._route_pick_mode:
            by_uid = {s["uid"]: s for s in self.state.stops}
            for i, uid in enumerate(self._route_pick_uids):
                s = by_uid.get(uid)
                if not s:
                    continue
                mark = "OK" if s.get("installed") else "SKIP" if s.get("skipped") else "--"
                self.list_route.addItem(
                    f"→ {i + 1}. [{letters.get(uid, '?')}] Site {s['id']} — {self._street_label(s)} [{mark}]")
            picked_set = set(self._route_pick_uids)
            for s in self.state.stops:
                if s["uid"] in picked_set:
                    continue
                self.list_route.addItem(
                    f"   [{letters.get(s['uid'], '?')}] Site {s['id']} — {self._street_label(s)}")
            return
        for i, s in enumerate(self.state.stops):
            mark = "OK" if s.get("installed") else "SKIP" if s.get("skipped") else "--"
            zone = s.get("route_zone")
            ztxt = f" Z{zone}" if zone else ""
            self.list_route.addItem(
                f"[{mark}] {i + 1}.{ztxt} Site {s['id']} - {self._street_label(s)}")
        miles = float(self.state.route.get("miles", 0.0) or 0)
        on_graph = bool(self.state.route.get("graph"))
        if self.state.stops:
            kind_short = "Roads" if on_graph else "Segments"
            kind_long = (
                "Real roads + segment lines"
                if on_graph
                else "Segment lines — import road map for streets"
            )
        else:
            kind_short = "—"
            kind_long = "Build route on Setup"
        if hasattr(self, "lbl_stat_stops") and self.lbl_stat_stops is not None:
            self.lbl_stat_stops.setText(str(len(self.state.stops)))
            self.lbl_stat_miles.setText(f"{miles:.1f}" if self.state.stops else "—")
            self.lbl_stat_kind.setText(kind_short)
        elif hasattr(self, "lbl_route_summary") and self.state.stops:
            self.lbl_route_summary.setText(
                f"{len(self.state.stops)} stops · {miles:.1f} mi · {kind_short}")
        elif hasattr(self, "lbl_route_summary"):
            self.lbl_route_summary.setText("")
        self.lbl_route_stats.setText(
            f"{len(self.state.stops)} stops - {miles:.1f} mi - {kind_long}"
        )
        self._refresh_route_summary_ui()
        self._refresh_workflow_strip()
        self._refresh_field_strip_ui()
        self._refresh_field_alerts()
        self.btn_start.setText("STOP FOLLOW" if self._gps_follow else "FOLLOW GPS")
        self.btn_start.setObjectName("stop" if self._gps_follow else "go")
        self.btn_start.setStyleSheet("")  # re-evaluate object-name style
        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)

    def _route_item_clicked(self, item):
        self.current_index = self.list_route.row(item)
        self._go_page(2)
        self._center_current()

    # ----------------------------------------------------- Map follow (GPS)
    def _toggle_drive(self):
        if self._gps_follow:
            self._stop_drive()
        else:
            self._start_drive()

    def _start_drive(self):
        if not self.state.stops:
            self._warn("Build a route first.")
            return
        if not self._next_leg_payload():
            self._info("All stops are already done.")
            return
        if not road_router.has_graph(DATA_DIR):
            if self.state.offline_mode:
                self._field_notice(
                    "Straight-line legs — no local road map on this laptop.")
            else:
                self._warn(
                    "No offline road map for this area yet.\n\n"
                    "On WiFi: Setup → Download road map → BUILD ROUTE.")
        self._gps_follow = True
        self.nav = {"active": True}
        self.bridge.set_follow(True)
        self._set_drive_mode(True)
        self._apply_power_profile()
        self._update_right(force_map=True)
        self._push_state()
        self._refresh_route_list()
        self._go_page(1)
        nxt = self._next_leg_payload()
        if nxt:
            self.statusBar().showMessage(
                f"Following GPS — next Site {nxt.get('to_id', '?')} "
                f"({nxt['miles']:.1f} mi). Map pans with you.",
                10000,
            )

    def _stop_drive(self):
        self._gps_follow = False
        self.nav = {"active": False}
        self._set_drive_mode(False)
        self.bridge.set_follow(False)
        self._apply_power_profile()
        self.btn_start.setText("FOLLOW GPS")
        self.btn_start.setObjectName("go")
        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)
        self._push_state()
        self.statusBar().showMessage("GPS follow stopped.", 5000)

    # ------------------------------------------------------- PicoCount counter
    def _counter_selected_port(self) -> str | None:
        if not hasattr(self, "combo_counter_port"):
            return None
        idx = self.combo_counter_port.currentIndex()
        if idx >= 0:
            data = self.combo_counter_port.itemData(idx)
            if data:
                return str(data)
        p = self.combo_counter_port.currentText().strip()
        if not p or p.startswith("("):
            return None
        return p.split(" ", 1)[0].strip()

    def _counter_list_ports(self) -> None:
        """List PicoCount COM ports only — GPS adapters stay out of the dropdown."""
        if not hasattr(self, "combo_counter_port"):
            return
        cur = self._counter_selected_port()
        self.combo_counter_port.clear()
        labeled = picocount.counter_ports_labeled()
        if not labeled:
            self.combo_counter_port.addItem("(none — plug PicoCount USB)")
        else:
            for device, label in labeled:
                self.combo_counter_port.addItem(label, device)
        if cur:
            for i in range(self.combo_counter_port.count()):
                if self.combo_counter_port.itemData(i) == cur:
                    self.combo_counter_port.setCurrentIndex(i)
                    break
        elif labeled:
            pref = picocount.preferred_counter_port([d for d, _ in labeled])
            if pref:
                for i in range(self.combo_counter_port.count()):
                    if self.combo_counter_port.itemData(i) == pref:
                        self.combo_counter_port.setCurrentIndex(i)
                        break

    def _counter_pause_gps(self) -> None:
        if self._gps_paused_for_counter:
            return
        self._gps_paused_for_counter = True
        self.gps.stop(join_timeout=3.5)

    def _counter_resume_gps(self) -> None:
        if not self._gps_paused_for_counter:
            return
        self._gps_paused_for_counter = False
        self.gps.start()

    def _counter_refresh_and_connect(self) -> None:
        crash_log.set_last_action("PicoCount refresh")
        self._counter_list_ports()
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        port = self._counter_selected_port()
        if not port:
            apply_counter_status(
                self.lbl_counter_status, "fail", "No PicoCount port — plug download USB cable.")
            return
        if picocount.is_gps_port(port):
            apply_counter_status(
                self.lbl_counter_status, "fail", f"{port} is GPS — select the PicoCount port.")
            return
        self._counter_set_busy("Refreshing counter… (GPS paused)")
        self._counter_pause_gps()
        QTimer.singleShot(1000, self._counter_connect_after_gps_pause)

    def _counter_connect_after_gps_pause(self) -> None:
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        port = self._counter_selected_port()

        def wrap(r):
            r["_op"] = "probe"
            self._on_picocount_done(r)

        thread = PicocountThread("probe", port=port)
        self._picocount_thread = thread
        thread.finished_result.connect(wrap)
        thread.start()

    def _planned_counter_unit_id(self) -> str:
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return ""
        s = self.state.stops[self.current_index]
        g = self.gps.latest()
        hdg = g.get("heading_display") or g.get("heading_locked") or g.get("heading")
        return picocount.build_unit_id(
            s.get("id", ""),
            self.combo_dir.currentText() if hasattr(self, "combo_dir") else "n",
            heading_deg=hdg,
        )

    def _update_counter_labels(self) -> None:
        if not hasattr(self, "lbl_counter_unit"):
            return
        uid = self._planned_counter_unit_id()
        on_stop = ""
        if self.state.stops and self.current_index < len(self.state.stops):
            s = self.state.stops[self.current_index]
            on_stop = str(s.get("counter_unit_id") or "").strip()
        if on_stop:
            self.lbl_counter_unit.setText(f"Unit ID on counter: {on_stop}")
        elif uid:
            self.lbl_counter_unit.setText(f"Next Unit ID (Auto-name / Clear): {uid}")
        else:
            self.lbl_counter_unit.setText("")
        if self.state.stops and self.current_index < len(self.state.stops):
            s = self.state.stops[self.current_index]
            parts = []
            sn = str(s.get("counter_serial") or s.get("serial") or "").strip()
            if sn:
                parts.append(f"Serial {sn}")
            if s.get("counter_unit_id"):
                parts.append(f"Unit ID {s['counter_unit_id']}")
            if s.get("counter_download_path"):
                parts.append("Data downloaded")
            if parts and hasattr(self, "lbl_counter_download"):
                self.lbl_counter_download.setText(" · ".join(parts))

    def _counter_set_busy(self, msg: str) -> None:
        apply_counter_status(self.lbl_counter_status, "busy", msg)
        for w in (
            self.btn_counter_refresh,
            self.btn_counter_clear,
            getattr(self, "btn_counter_autoname", None),
            getattr(self, "btn_counter_download", None),
        ):
            if w is not None:
                w.setEnabled(False)

    def _counter_clear_busy(self) -> None:
        for w in (
            self.btn_counter_refresh,
            self.btn_counter_clear,
            getattr(self, "btn_counter_autoname", None),
            getattr(self, "btn_counter_download", None),
        ):
            if w is not None:
                w.setEnabled(True)
        if hasattr(self, "btn_counter_download"):
            self.btn_counter_download.setEnabled(self._counter_connected)
        self._update_counter_labels()

    def _counter_show_memory(self, res: dict | None = None) -> None:
        if not hasattr(self, "lbl_counter_data"):
            return
        if res is not None:
            if res.get("ok"):
                self._counter_memory_bytes = int(res.get("bytes") or 0)
            else:
                self._counter_memory_bytes = None
        b = self._counter_memory_bytes
        if b is None:
            self.lbl_counter_data.setText("")
            return
        if b <= 0:
            self.lbl_counter_data.setText("Counter data: 0 bytes — empty")
            self.lbl_counter_data.setProperty("counterEmpty", "true")
        else:
            self.lbl_counter_data.setText(f"Counter data: ~{b:,} bytes stored")
            self.lbl_counter_data.setProperty("counterEmpty", "false")
        st = self.lbl_counter_data.style()
        st.unpolish(self.lbl_counter_data)
        st.polish(self.lbl_counter_data)

    def _on_picocount_done(self, res: dict) -> None:
        self._picocount_thread = None
        op = res.pop("_op", "")
        resume_gps = True
        try:
            self._on_picocount_done_body(res, op, resume_gps_holder := {"v": True})
            resume_gps = resume_gps_holder["v"]
        except Exception as exc:  # noqa: BLE001
            path = crash_log.log_error(exc, context=f"picocount_{op or 'unknown'}")
            apply_counter_status(
                self.lbl_counter_status,
                "fail",
                f"Counter error — see {os.path.basename(path)} in tds_data/crashes/",
            )
            self._warn(
                f"PicoCount operation failed safely (app kept running).\n\n"
                f"Log saved:\n{path}")
        finally:
            if resume_gps:
                self._counter_resume_gps()
        self._counter_clear_busy()
        self._update_counter_labels()
        self._refresh_install_checklist()
        self._refresh_field_alerts()

    def _on_picocount_done_body(self, res: dict, op: str, resume_gps_holder: dict) -> None:
        if op == "probe":
            self._set_counter_connected_ui(bool(res.get("ok")))
            if res.get("ok"):
                self._counter_show_memory(res)
                unit = str(res.get("unit_id") or "").strip()
                sn = str(res.get("serial_number") or "").strip()
                mem = res.get("label") or "connected"
                if sn and hasattr(self, "txt_serial"):
                    self.txt_serial.setText(sn)
                if sn and self.state.stops and self.current_index < len(self.state.stops):
                    s = self.state.stops[self.current_index]
                    s["counter_serial"] = sn
                    s["serial"] = sn
                    self._persist_shift(quiet=True)
                parts = [mem]
                if sn:
                    parts.append(f"Serial {sn}")
                if unit:
                    parts.append(f"Unit ID {unit}")
                apply_counter_status(
                    self.lbl_counter_status,
                    "ok",
                    "Connected — " + " · ".join(parts),
                )
                self.statusBar().showMessage("PicoCount connected.", 6000)
                if (
                    self._counter_selected_port()
                    and not sn
                    and hasattr(self, "txt_serial")
                    and not self.txt_serial.text().strip()
                ):
                    resume_gps_holder["v"] = False
                    self._counter_read_serial(auto=True)
            else:
                self._counter_show_memory(None)
                apply_counter_status(
                    self.lbl_counter_status,
                    "fail",
                    res.get("error") or res.get("message", "Not connected"),
                )
        elif op == "serial":
            if res.get("ok"):
                sn = str(res.get("serial_number", "")).strip()
                if sn and hasattr(self, "txt_serial"):
                    self.txt_serial.setText(sn)
                if self.state.stops and self.current_index < len(self.state.stops):
                    s = self.state.stops[self.current_index]
                    if sn:
                        s["counter_serial"] = sn
                        s["serial"] = sn
                    self._persist_shift(quiet=True)
                apply_counter_status(
                    self.lbl_counter_status,
                    "ok",
                    f"Serial {sn or '—'} · {res.get('model', '')} {res.get('firmware', '')}",
                )
                self.statusBar().showMessage("Counter serial read.", 5000)
            else:
                apply_counter_status(
                    self.lbl_counter_status,
                    "fail",
                    res.get("error", "Serial read failed"),
                )
        elif op == "clear_configure":
            if res.get("ok"):
                self._counter_memory_bytes = int(res.get("bytes_after") or 0)
                self._counter_show_memory()
                if self.state.stops and self.current_index < len(self.state.stops):
                    s = self.state.stops[self.current_index]
                    s["counter_unit_id"] = res.get("unit_id", "")
                    s["counter_serial"] = res.get("serial_number", s.get("counter_serial", ""))
                    if res.get("serial_number"):
                        s["serial"] = str(res["serial_number"])
                    s["counter_cleared_at"] = ca_now()[1]
                    if res.get("serial_number") and hasattr(self, "txt_serial"):
                        self.txt_serial.setText(str(res["serial_number"]))
                    self._persist_shift(quiet=True)
                before = int(res.get("bytes_before") or 0)
                after = int(res.get("bytes_after") or 0)
                apply_counter_status(
                    self.lbl_counter_status,
                    "ok",
                    f"Cleared {before:,} → {after:,} bytes · Unit ID {res.get('unit_id', '')}",
                )
                self.statusBar().showMessage("Counter cleared and configured for this site.", 8000)
            else:
                apply_counter_status(
                    self.lbl_counter_status,
                    "fail",
                    res.get("error", "Clear/configure failed"),
                )
                self._warn(res.get("error", "Counter operation failed"))
        elif op == "rename":
            if res.get("ok"):
                if self.state.stops and self.current_index < len(self.state.stops):
                    s = self.state.stops[self.current_index]
                    s["counter_unit_id"] = res.get("unit_id", "")
                    sn = str(res.get("serial_number") or "").strip()
                    if sn:
                        s["counter_serial"] = sn
                        s["serial"] = sn
                        if hasattr(self, "txt_serial"):
                            self.txt_serial.setText(sn)
                    self._persist_shift(quiet=True)
                apply_counter_status(
                    self.lbl_counter_status,
                    "ok",
                    f"Unit ID set to {res.get('unit_id', '')}",
                )
                self.statusBar().showMessage("Counter renamed for this site.", 6000)
            else:
                apply_counter_status(
                    self.lbl_counter_status,
                    "fail",
                    res.get("error", "Rename failed"),
                )
                self._warn(res.get("error", "Could not rename counter"))
        elif op == "download":
            if res.get("ok"):
                if self.state.stops and self.pickup_index < len(self._installed_stops()):
                    items = self._installed_stops()
                    s = items[min(self.pickup_index, len(items) - 1)]
                    s["counter_download_path"] = res.get("path", "")
                    self._persist_shift(quiet=True)
                    self._refresh_pickup()
                apply_counter_status(
                    self.lbl_counter_status,
                    "ok",
                    f"Downloaded {res.get('bytes', 0):,} bytes → {os.path.basename(res.get('path', ''))}",
                )
                self.statusBar().showMessage("Counter data saved locally.", 8000)
            else:
                apply_counter_status(
                    self.lbl_counter_status,
                    "fail",
                    res.get("error", "Download failed"),
                )
                self._warn(res.get("error", "Could not download counter data"))

    def _counter_read_serial(self, *, auto: bool = False) -> None:
        if auto and not hasattr(self, "txt_serial"):
            return
        if auto and self.txt_serial.text().strip():
            return
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        if not auto:
            self._counter_set_busy("Reading counter serial (slow)…")
        self._counter_pause_gps()

        def wrap(r):
            r["_op"] = "serial"
            self._on_picocount_done(r)

        thread = PicocountThread("serial", port=self._counter_selected_port())
        self._picocount_thread = thread
        thread.finished_result.connect(wrap)
        thread.start()

    def _counter_clear_configure(self) -> None:
        uid = self._planned_counter_unit_id()
        if not uid:
            self._warn("Select a stop first.")
            return
        if not self._counter_connected:
            self._warn("Connect counter first — tap Refresh.")
            return
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        crash_log.set_last_action(f"PicoCount clear {uid}")
        self._counter_set_busy(f"Clearing counter · {uid}… (GPS paused)")
        self._counter_pause_gps()
        QTimer.singleShot(1000, self._counter_clear_configure_after_pause)

    def _counter_clear_configure_after_pause(self) -> None:
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        uid = self._planned_counter_unit_id()
        if not uid:
            self._counter_resume_gps()
            self._counter_clear_busy()
            return

        def wrap(r):
            r["_op"] = "clear_configure"
            self._on_picocount_done(r)

        thread = PicocountThread(
            "clear_configure",
            port=self._counter_selected_port(),
            unit_id=uid,
        )
        self._picocount_thread = thread
        thread.finished_result.connect(wrap)
        thread.start()

    def _counter_autoname(self) -> None:
        uid = self._planned_counter_unit_id()
        if not uid:
            self._warn("Select a stop first.")
            return
        if not self._counter_connected:
            self._warn("Connect counter first — tap Refresh.")
            return
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        self._counter_set_busy(f"Naming counter · {uid}…")
        self._counter_pause_gps()

        def wrap(r):
            r["_op"] = "rename"
            self._on_picocount_done(r)

        thread = PicocountThread(
            "rename",
            port=self._counter_selected_port(),
            unit_id=uid,
        )
        self._picocount_thread = thread
        thread.finished_result.connect(wrap)
        thread.start()

    def _counter_download_pickup(self) -> None:
        items = self._installed_stops()
        if not items or self.pickup_index >= len(items):
            self._warn("Select an installed site on Pickup first.")
            return
        s = items[self.pickup_index]
        os.makedirs(COUNTER_DOWNLOAD_DIR, exist_ok=True)
        fname = f"site_{s.get('id', 'x')}_{s.get('counter_unit_id', 'data')}.pcbin"
        fname = "".join(c if c.isalnum() or c in "._-" else "_" for c in fname)
        dest = os.path.join(COUNTER_DOWNLOAD_DIR, self.state.profile, fname)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        self._counter_set_busy("Downloading counter data…")
        self._counter_pause_gps()
        meta = {
            "site_id": s.get("id"),
            "unit_id": s.get("counter_unit_id"),
            "street": s.get("street"),
        }

        def wrap(r):
            r["_op"] = "download"
            self._on_picocount_done(r)

        thread = PicocountThread(
            "download",
            port=self._counter_selected_port(),
            dest_path=dest,
            meta=meta,
        )
        self._picocount_thread = thread
        thread.finished_result.connect(wrap)
        thread.start()

    # ------------------------------------------------------- Install UI/flow
    def _refresh_install(self):
        done, total = self.state.progress_install()
        if not self.state.stops or self.current_index >= len(self.state.stops):
            self.lbl_install_title.setText("No stop selected.")
            self.lbl_install_prog.setText("")
            if hasattr(self, "lbl_cross_hint"):
                self.lbl_cross_hint.setText("")
            return
        s = self.state.stops[self.current_index]
        seq = self.current_index + 1
        self.lbl_install_title.setText(
            f"Stop {seq}/{total} · Site {s['id']}")
        side = str(s.get("cross_side") or "").strip()
        cross_txt = ""
        if s.get("cross_lat") is not None:
            cross_txt = (
                f"Drive-to on line"
                f"{f' ({side})' if side else ''}")
        from ui.simple_mode import COMPACT_UI
        if COMPACT_UI:
            prog = f"{self._street_label(s)} · {done}/{total} done"
            if not s.get("cross_lat"):
                prog += " · build route for crossing"
            self.lbl_install_prog.setText(prog)
            if hasattr(self, "lbl_cross_hint"):
                self.lbl_cross_hint.setText("")
        else:
            self.lbl_cross_hint.setText(
                cross_txt or "Crossing not set — BUILD ROUTE after road map download.")
            self.lbl_install_prog.setText(
                f"{s.get('sheet', '')} · {self._street_label(s)} · {done}/{total} installed")
        raw = str(s.get("street", "")).strip()
        self.txt_street.setText(raw if raw and raw.lower() not in ("nan", "none", "nat") else "")
        raw_dir = str(s.get("direction") or "").strip().lower()
        if raw_dir not in DIRECTIONS:
            raw_dir = "n"
        self.combo_dir.blockSignals(True)
        self.combo_dir.setCurrentText(raw_dir)
        self.combo_dir.blockSignals(False)
        g_snap = self.gps.latest()
        hdg = g_snap.get("heading_display") or g_snap.get("heading_locked") or g_snap.get("heading")
        src = str(s.get("direction_source") or "")
        if (
            not s.get("installed")
            and src != "manual"
            and hdg is not None
            and g_snap.get("heading_mode") == "locked"
        ):
            hint = direction_rules.infer_from_heading(hdg)
            self.combo_dir.blockSignals(True)
            self.combo_dir.setCurrentText(hint["direction"])
            self.combo_dir.blockSignals(False)
            s["direction"] = hint["direction"]
            s["direction_source"] = "gps"
        if hasattr(self, "lbl_direction_hint"):
            self.lbl_direction_hint.setText(direction_rules.direction_hint_text(s))
        self.spin_lanes.setValue(int(s.get("lanes", 2)))
        self.txt_serial.setText(str(s.get("serial", "")))
        self.txt_notes.setPlainText(str(s.get("notes", "")))
        fl, fo = s.get("field_lat"), s.get("field_lon")
        if fl:
            src = str(s.get("field_coord_source") or "gps")
            prefix = "Manual GPS" if src == "manual" else "Field GPS"
            self.lbl_grab.setText(f"{prefix}: {fl:.5f}, {fo:.5f}")
        else:
            self.lbl_grab.setText("")
        warn = str(s.get("street_warning") or "").strip()
        if not warn and road_router.has_graph(DATA_DIR):
            try:
                from core import street_intel
                g = road_router.load_graph(DATA_DIR)
                cross = None
                if s.get("cross_lat") is not None:
                    cross = (float(s["cross_lat"]), float(s["cross_lon"]))
                r = street_intel.analyze_segment(
                    g,
                    (float(s["begin_lat"]), float(s["begin_lon"])),
                    (float(s["end_lat"]), float(s["end_lon"])),
                    cross,
                )
                warn = str(r.get("message") or "").strip()
                if warn:
                    s["street_warning"] = warn
            except Exception:
                pass
        self.lbl_street_warn.setText(warn)
        self.lbl_street_warn.setVisible(bool(warn))
        self._refresh_install_checklist()
        self._update_compass_labels(self.gps.latest())
        self._update_counter_labels()
        self._counter_show_memory()
        if self.state.stops and self.current_index < len(self.state.stops):
            s = self.state.stops[self.current_index]
            uid = s.get("uid")
            if uid != self._counter_serial_grab_uid and not str(s.get("serial", "")).strip():
                self._counter_serial_grab_uid = uid
                QTimer.singleShot(600, lambda: self._counter_read_serial(auto=True))

    def _on_install_dir_changed(self, *_):
        if self.state.stops and self.current_index < len(self.state.stops):
            s = self.state.stops[self.current_index]
            s["direction"] = self.combo_dir.currentText()
            s["direction_source"] = "manual"
            if hasattr(self, "lbl_direction_hint"):
                self.lbl_direction_hint.setText(direction_rules.direction_hint_text(s))
        self._schedule_autosave()
        self._update_counter_labels()

    def _refresh_install_checklist(self) -> None:
        if not hasattr(self, "lbl_install_checklist"):
            return
        if not self.state.stops or self.current_index >= len(self.state.stops):
            self.lbl_install_checklist.setText("")
            return
        s = self.state.stops[self.current_index]
        if hasattr(self, "txt_serial") and self.txt_serial.text().strip():
            sn = self.txt_serial.text().strip()
            s["serial"] = sn
            s["counter_serial"] = sn
        items = install_checklist.checklist_for_stop(s)
        self.lbl_install_checklist.setText(install_checklist.format_checklist_text(items))
        ready = install_checklist.all_ready(items)
        self.lbl_install_checklist.setProperty("allReady", "true" if ready else "false")
        st = self.lbl_install_checklist.style()
        st.unpolish(self.lbl_install_checklist)
        st.polish(self.lbl_install_checklist)

    def _set_dir_from_compass(self):
        g = self.gps.latest()
        hdg = g.get("heading_display") or g.get("heading_locked") or g.get("heading")
        if hdg is None:
            self._warn("No compass reading yet. Drive a short distance, then stop.")
            return
        hint = direction_rules.infer_from_heading(hdg)
        self.combo_dir.setCurrentText(hint["direction"])
        if self.state.stops and self.current_index < len(self.state.stops):
            s = self.state.stops[self.current_index]
            s["direction"] = hint["direction"]
            s["direction_source"] = "gps"
            if hasattr(self, "lbl_direction_hint"):
                self.lbl_direction_hint.setText(direction_rules.direction_hint_text(s))
        self._schedule_autosave()
        self._update_counter_labels()
        card = self._heading_cardinal(hdg)
        self.statusBar().showMessage(
            f"Direction {hint['direction']} from compass: {hdg:.0f}° ({card})", 5000)

    def _manual_grab_prompt(self) -> str:
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return "Manual Grab — click the street on the map"
        s = self.state.stops[self.current_index]
        return f"Manual Grab — Site {s.get('id', '?')}: click the street on the map"

    def _sync_manual_grab_btn(self) -> None:
        btn = getattr(self, "btn_manual_grab", None)
        if btn is None:
            return
        on = self._manual_grab_mode
        btn.setChecked(on)
        btn.setText("Cancel grab" if on else "Manual Grab")

    def _end_manual_grab(self, *, silent: bool = False) -> None:
        if not self._manual_grab_mode:
            return
        self._manual_grab_mode = False
        self._sync_manual_grab_btn()
        self._push_state()
        if not silent:
            self.statusBar().showMessage("Manual Grab cancelled.", 4000)

    def _begin_manual_grab(self) -> None:
        if not self.state.stops or self.current_index >= len(self.state.stops):
            self._warn("No stop selected — build a route first.")
            return
        if self._route_pick_mode:
            self._warn("Finish route pick first, or clear pick mode.")
            return
        self._manual_grab_mode = True
        self._sync_manual_grab_btn()
        s = self.state.stops[self.current_index]
        lat, lon = self.state.point(s)
        self.bridge.fly_to(lat, lon, 16)
        online = self._internet_allowed()
        hint = (
            "Click the street on the map for install GPS."
            if online
            else "Offline — click the street; street name updates when you tap I'm online."
        )
        self.statusBar().showMessage(hint, 8000)
        self._push_state()

    def _toggle_manual_grab(self) -> None:
        if self._manual_grab_mode:
            self._end_manual_grab()
        else:
            self._begin_manual_grab()

    def _manual_grab_at(self, lat: float, lon: float) -> None:
        if not self.state.stops or self.current_index >= len(self.state.stops):
            self._end_manual_grab(silent=True)
            return
        if not self._save_field_position(lat, lon, source="manual"):
            return
        self._end_manual_grab(silent=True)
        self.statusBar().showMessage("Manual Grab saved — install position set on map.", 6000)

    def _retry_pending_field_geocode(self) -> None:
        """When Wi‑Fi returns, reverse-geocode street for a manual/offline grab."""
        if not self._internet_allowed():
            return
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return
        s = self.state.stops[self.current_index]
        if not s.get("field_geocode_pending"):
            return
        lat, lon = s.get("field_lat"), s.get("field_lon")
        if lat is None or lon is None:
            s["field_geocode_pending"] = False
            return
        online_street = geo.street_from_coords(float(lat), float(lon))
        if not online_street:
            return
        self.txt_street.setText(online_street)
        s["field_geocode_pending"] = False
        self._flush_install_form()
        self._persist_shift(quiet=True)
        self._refresh_install_checklist()
        if hasattr(self, "lbl_grab"):
            self.lbl_grab.setText(f"Manual GPS: {float(lat):.5f}, {float(lon):.5f}")
        self.statusBar().showMessage(
            "Wi‑Fi on — street name updated from online geocode.", 6000)

    def _save_field_position(self, lat: float, lon: float, *, source: str = "gps") -> bool:
        """Persist install field_lat/lon and resolve street (online/offline/excel)."""
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return False
        lat, lon = geo.normalize_ca_coords(float(lat), float(lon))
        if not geo.ca_coords_plausible(lat, lon):
            self._warn("That point is outside California — click a street on the map.")
            return False
        s = self.state.stops[self.current_index]
        s["field_lat"], s["field_lon"] = lat, lon
        s["field_coord_source"] = source
        label = "Manual GPS" if source == "manual" else "Field GPS"
        self.lbl_grab.setText(f"{label}: {lat:.5f}, {lon:.5f}")
        prefer_online = self._internet_allowed()
        street, src_tag = geo.street_for_field(lat, lon, DATA_DIR, prefer_online=prefer_online)
        if street:
            self.txt_street.setText(street)
            s["field_geocode_pending"] = False
            hint = "online" if src_tag == "online" else "offline road map"
            self.statusBar().showMessage(f"Install GPS saved — street from {hint}.", 5000)
        else:
            excel_st = str(s.get("street", "")).strip()
            if excel_st and not excel_st.lower().startswith("site "):
                self.txt_street.setText(excel_st)
                s["field_geocode_pending"] = not prefer_online
                self.statusBar().showMessage("Install GPS saved — street from Excel.", 5000)
            else:
                s["field_geocode_pending"] = not prefer_online
                self.statusBar().showMessage(
                    "Install GPS saved. Type street or tap I'm online for geocode.", 6000)
        if road_router.has_graph(DATA_DIR):
            try:
                from core import street_intel
                g = road_router.load_graph(DATA_DIR)
                r = street_intel.analyze_point(g, lat, lon)
                msg = str(r.get("message") or "").strip()
                if msg:
                    s["street_warning"] = msg
                    self.lbl_street_warn.setText(msg)
                    self.lbl_street_warn.setVisible(True)
            except Exception:
                pass
        self._flush_install_form()
        self._persist_shift(quiet=True)
        self._push_state()
        self._refresh_install_checklist()
        return True

    def _grab_gps_here(self):
        if not self.state.stops or self.current_index >= len(self.state.stops):
            self._warn("No stop selected — build a route first.")
            return
        g = self.gps.latest()
        fix = gps_reader.fix_from_snapshot(g)
        if fix is None:
            if hasattr(self, "lbl_grab"):
                self.lbl_grab.setText("No GPS fix")
            self._warn(gps_reader.no_fix_message(g))
            return
        lat, lon = fix
        sats = g.get("satellites", 0) if g.get("fix") else 0
        if self._save_field_position(lat, lon, source="gps") and hasattr(self, "lbl_grab"):
            fl, fo = lat, lon
            self.lbl_grab.setText(f"Field GPS: {fl:.5f}, {fo:.5f}  ({sats} sats)")

    def _commit_install(self, installed: bool):
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return
        s = self.state.stops[self.current_index]
        self._flush_install_form()
        self._sync_counter_fields(s)
        notes = self.txt_notes.toPlainText()
        d, lanes, serial = geo.parse_dictation(notes, self.combo_dir.currentText(),
                                               self.spin_lanes.value(), self.txt_serial.text())
        if serial:
            s["serial"] = serial
            s["counter_serial"] = serial
        if installed:
            block = install_checklist.install_block_reason(s)
            if block:
                self._field_notice(
                    f"Complete checklist first: {block} — then tap INSTALL.", 9000)
                return
        if installed and serial:
            dup = install_checklist.find_duplicate_serial(
                self.state.stops, s["uid"], serial)
            if dup:
                street = self._street_label(dup)
                if QMessageBox.question(
                    self,
                    "Duplicate counter serial",
                    f"Serial {serial} is already on Site {dup.get('id')} ({street}).\n\n"
                    "Install on this site anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                ) != QMessageBox.Yes:
                    return
        unit_id = str(s.get("counter_unit_id") or "").strip()
        if installed and unit_id:
            dup_uid = install_checklist.find_duplicate_unit_id(
                self.state.stops, s["uid"], unit_id)
            if dup_uid:
                street = self._street_label(dup_uid)
                if QMessageBox.question(
                    self,
                    "Duplicate Unit ID",
                    f"Unit ID {unit_id} is already on Site {dup_uid.get('id')} ({street}).\n\n"
                    "Install anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                ) != QMessageBox.Yes:
                    return
        self._push_undo(
            "install" if installed else "skip",
            s["uid"],
            self._snapshot_stop(s),
            site_id=s["id"],
            current_index=self.current_index,
        )
        date, exact = ca_now()
        s.update({"street": self.txt_street.text().strip(), "direction": d, "lanes": lanes,
                  "serial": s.get("serial", serial), "notes": notes,
                  "installed": installed, "skipped": not installed,
                  "date": date, "exact_time": exact})
        self._sync_counter_fields(s)
        self._persist_shift(quiet=True)
        self._push_state()
        self._refresh_route_list()
        self._refresh_audit()
        self._refresh_field_alerts()
        verb = "Installed" if installed else "Skipped"
        self.statusBar().showMessage(
            f"Site {s.get('id', '?')} {verb} — saved locally.", 8000)
        if installed:
            self._maybe_export_nudge()
        self._nav_install(1)

    def _nav_install(self, step: int):
        if not self.state.stops:
            return
        self._flush_install_form()
        self._persist_shift(quiet=True)
        self.current_index = max(0, min(len(self.state.stops) - 1, self.current_index + step))
        self._end_manual_grab(silent=True)
        self._refresh_install()
        self._center_current()

    def _center_current(self):
        if self.state.stops and self.current_index < len(self.state.stops):
            lat, lon = self.state.point(self.state.stops[self.current_index])
            self.bridge.fly_to(lat, lon, 13)

    # -------------------------------------------------------- Pickup UI/flow
    def _installed_stops(self):
        items = [s for s in self.state.stops if s.get("installed")]
        if getattr(self, "chk_pickup_pending", None) and self.chk_pickup_pending.isChecked():
            items = [s for s in items if not s.get("picked_up")]
        return items

    def _refresh_pickup(self):
        self._update_counter_labels()
        done, total = self.state.progress_pickup()
        pending = sum(1 for s in self.state.stops if s.get("installed") and not s.get("picked_up"))
        self.lbl_pickup_prog.setText(f"Pick-up progress: {done}/{total}  ({pending} pending)")
        self.list_pickup.clear()
        for i, s in enumerate(self._installed_stops()):
            mark = "OK" if s.get("picked_up") else "--"
            self.list_pickup.addItem(f"[{mark}] {i + 1}. Site {s['id']} - {self._street_label(s)}")
        self._refresh_pickup_cur()
        self._refresh_field_alerts()

    def _refresh_pickup_cur(self):
        items = self._installed_stops()
        if items and self.pickup_index < len(items):
            s = items[self.pickup_index]
            self.lbl_pickup_cur.setText(f"Current: Site {s['id']} - {self._street_label(s)}")
        else:
            self.lbl_pickup_cur.setText("No pick-up selected.")

    def _pickup_item_clicked(self, item):
        self.pickup_index = self.list_pickup.row(item)
        self._refresh_pickup_cur()
        items = self._installed_stops()
        if self.pickup_index < len(items):
            lat, lon = self.state.point(items[self.pickup_index])
            self.bridge.fly_to(lat, lon, 13)

    def _mark_pickup(self):
        items = self._installed_stops()
        if not items or self.pickup_index >= len(items):
            return
        s = items[self.pickup_index]
        self._push_undo(
            "pickup",
            s["uid"],
            self._snapshot_stop(s),
            site_id=s["id"],
            pickup_index=self.pickup_index,
        )
        s["picked_up"] = True
        self._persist_shift(quiet=True)
        self.pickup_index = min(len(items) - 1, self.pickup_index + 1)
        self._refresh_pickup()
        self._push_state()
        self._refresh_audit()

    def _nav_pickup(self, step: int):
        items = self._installed_stops()
        if not items:
            return
        self.pickup_index = max(0, min(len(items) - 1, self.pickup_index + step))
        self._refresh_pickup_cur()
        lat, lon = self.state.point(items[self.pickup_index])
        self.bridge.fly_to(lat, lon, 14)

    # ------------------------------------------------------- Undo / shortcuts
    @staticmethod
    def _snapshot_stop(s: dict) -> dict:
        return {k: s.get(k) for k in UNDO_FIELDS}

    def _push_undo(self, kind: str, uid: str, snapshot: dict, **extra):
        self._undo_stack.append({"kind": kind, "uid": uid, "snapshot": snapshot, **extra})
        if len(self._undo_stack) > 20:
            self._undo_stack.pop(0)
        self._refresh_undo_ui()

    def _refresh_undo_ui(self):
        enabled = bool(self._undo_stack)
        tip = ""
        if self._undo_stack:
            last = self._undo_stack[-1]
            tip = f"Undo {last['kind']} — Site {last.get('site_id', '?')}"
        for attr in ("btn_undo_install", "btn_undo_pickup"):
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setEnabled(enabled)
                btn.setToolTip(tip)

    def _undo_last_action(self):
        if not self._undo_stack:
            return
        entry = self._undo_stack.pop()
        idx = self.state.index_of(entry["uid"])
        if idx < 0:
            self._warn("That stop is no longer in the route.")
            self._refresh_undo_ui()
            return
        s = self.state.stops[idx]
        s.update(entry["snapshot"])
        kind = entry["kind"]
        if kind in ("install", "skip"):
            self.current_index = entry.get("current_index", idx)
            self._go_page(2)
            self._refresh_install()
            self._center_current()
        elif kind == "pickup":
            self.pickup_index = entry.get("pickup_index", 0)
            self._go_page(3)
            self._refresh_pickup()
        self._persist_shift(quiet=True)
        self._push_state()
        self._refresh_route_list()
        self._refresh_audit()
        self._refresh_undo_ui()
        self.statusBar().showMessage(
            f"Undid {kind} on Site {entry.get('site_id', '')}.", 6000)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Z"), self, self._undo_last_action)
        QShortcut(QKeySequence("I"), self, self._shortcut_install)
        QShortcut(QKeySequence("S"), self, self._shortcut_skip)
        QShortcut(QKeySequence("G"), self, self._shortcut_grab_gps)
        QShortcut(QKeySequence("M"), self, self._shortcut_manual_grab)
        QShortcut(QKeySequence("N"), self, self._shortcut_prev_stop)
        QShortcut(QKeySequence("P"), self, self._shortcut_next_stop)

    def _shortcut_install(self):
        if self.pages.currentIndex() == 2:
            self._commit_install(True)

    def _shortcut_skip(self):
        if self.pages.currentIndex() == 2:
            self._commit_install(False)

    def _shortcut_grab_gps(self):
        if self.pages.currentIndex() == 2:
            self._grab_gps_here()

    def _shortcut_manual_grab(self):
        if self.pages.currentIndex() == 2:
            self._toggle_manual_grab()

    def _shortcut_prev_stop(self):
        if self.pages.currentIndex() == 2:
            self._nav_install(-1)
        elif self.pages.currentIndex() == 3:
            self._nav_pickup(-1)

    def _shortcut_next_stop(self):
        if self.pages.currentIndex() == 2:
            self._nav_install(1)
        elif self.pages.currentIndex() == 3:
            self._nav_pickup(1)

    def _phone_nav_links(self, kind: str = "install") -> tuple[list[dict], list[str]]:
        if not self.state.stops:
            return [], ["Build your route first (Setup → BUILD ROUTE)."]
        if kind == "pickup":
            batch = maps_links.pickup_sequence_stops(self.state.stops)
            if not batch:
                return [], ["No installed sites yet — install counters first."]
        else:
            batch = maps_links.install_sequence_stops(self.state.stops)
        return maps_links.build_route_links(batch)

    def _save_nav_links_page(self, kind: str) -> None:
        links, errors = self._phone_nav_links(kind)
        if errors and not links:
            self._warn("Cannot build phone links:\n\n" + "\n".join(errors))
            return
        miles = float(self.state.route.get("miles", 0) or 0)
        body = maps_links.to_html(
            links,
            profile=self.state.profile,
            miles=miles if miles > 0 and kind == "install" else None,
            kind=kind,
        )
        default = maps_links.default_links_path(DATA_DIR, self.state.profile, kind=kind)
        dlg_title = "Save install navigation links" if kind == "install" else "Save pickup navigation links"
        path, _ = QFileDialog.getSaveFileName(self, dlg_title, default, "Web page (*.html)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        msg = f"Saved {len(links)} stop link(s).\n\n{path}"
        if errors:
            msg += "\n\nSkipped:\n" + "\n".join(errors)
        msg += "\n\nTip: send this file to your phone and tap each stop (Google Maps needs Wi‑Fi or cellular)."
        if not self._internet_allowed():
            msg += "\n\nField mode — links open on your phone when it has network."
        self._info(msg)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _save_install_nav_links(self) -> None:
        self._save_nav_links_page("install")

    def _save_pickup_nav_links(self) -> None:
        self._save_nav_links_page("pickup")

    # ---------------------------------------------------------- Audit/export
    def _refresh_audit(self):
        summ = shift_summarize(self.state.stops, self.state.route)
        if hasattr(self, "lbl_shift_summary"):
            self.lbl_shift_summary.setText(summ["text"])
        rep = export.audit(self.state.stops)
        if not self.state.stops:
            audit_txt = "No data yet."
        elif rep["missing"]:
            audit_txt = "ACTION NEEDED:\n- " + "\n- ".join(rep["missing"])
        else:
            audit_txt = f"All {rep['count']} completed sites have full data. Ready to export."
        self.lbl_audit.setText(audit_txt)
        self._refresh_export_hint()
        self._refresh_field_alerts()

    def _refresh_export_hint(self):
        if not hasattr(self, "lbl_export_hint"):
            return
        folder = export.export_dir(DATA_DIR)
        xlsx = export.default_report_path(DATA_DIR, self.state.profile, "xlsx")
        self.lbl_export_hint.setText(f"Default folder:\n{folder}\n\nNext quick export:\n{os.path.basename(xlsx)}")

    def _export_excel(self):
        data, err = export.to_excel_result(self.state.stops)
        if data is None:
            if err:
                self._warn(err)
            else:
                self._warn("Nothing to export yet (no installed/skipped sites).")
            return
        default = export.default_report_path(DATA_DIR, self.state.profile, "xlsx")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save report", default, "Excel (*.xlsx)")
        if path:
            with open(path, "wb") as f:
                f.write(data)
            self._info(f"Excel report saved.\n\n{path}")

    def _export_excel_quick(self):
        data, err = export.to_excel_result(self.state.stops)
        if data is None:
            if err:
                self._warn(err)
            else:
                self._warn("Nothing to export yet (no installed/skipped sites).")
            return
        path = export.default_report_path(DATA_DIR, self.state.profile, "xlsx")
        with open(path, "wb") as f:
            f.write(data)
        self._refresh_export_hint()
        self._info(f"Excel saved to default folder:\n\n{path}")

    def _export_csv(self):
        text = export.to_csv_text(self.state.stops)
        if not text.strip() or text.count("\n") <= 1:
            self._warn("Nothing to export yet (no installed/skipped sites).")
            return
        default = export.default_report_path(DATA_DIR, self.state.profile, "csv")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save report", default, "CSV (*.csv)")
        if path:
            with open(path, "w", newline="", encoding="utf-8") as f:
                f.write(text)
            self._info(f"CSV report saved.\n\n{path}")

    def _export_csv_quick(self):
        text = export.to_csv_text(self.state.stops)
        if not text.strip() or text.count("\n") <= 1:
            self._warn("Nothing to export yet (no installed/skipped sites).")
            return
        path = export.default_report_path(DATA_DIR, self.state.profile, "csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write(text)
        self._refresh_export_hint()
        self._info(f"CSV saved to default folder:\n\n{path}")

    # ------------------------------------------------------------- view theme
    def _sync_theme_buttons(self):
        t = normalize_theme(self.state.theme)
        for key, btn in self._theme_btns.items():
            btn.setChecked(key == t)

    def _refresh_theme_labels(self):
        t = normalize_theme(self.state.theme)
        if t == "night":
            sub, hint, warn, on = "#9aa3b2", "#9aa3b2", "#f87171", "#4ade80"
        elif t == "cloudy":
            sub, hint, warn, on = "#475569", "#475569", "#b91c1c", "#047857"
        else:
            sub, hint, warn, on = "#5c4f3a", "#5c4f3a", "#b91c1c", "#15803d"
        if hasattr(self, "lbl_save_hint"):
            self.lbl_save_hint.setStyleSheet(f"color:{hint};font-size:12px;font-weight:600;")
        if hasattr(self, "lbl_compass_sub"):
            self.lbl_compass_sub.setStyleSheet(f"color:{sub};font-size:12px;")
        if hasattr(self, "lbl_street_warn"):
            self.lbl_street_warn.setStyleSheet(f"color:{warn};font-weight:700;")
        if hasattr(self, "lbl_offline") and self.state.offline_mode:
            self.lbl_offline.setStyleSheet(f"color:{on};font-weight:700;")

    def _set_view_theme(self, theme: str):
        t = normalize_theme(theme)
        if t == normalize_theme(self.state.theme):
            self._sync_theme_buttons()
            return
        self.state.theme = t
        self.setStyleSheet(qt_stylesheet(t))
        self._sync_theme_buttons()
        self._refresh_theme_labels()
        self._refresh_offline_ui()
        self.state.save()
        labels = {"sunny": "Sunny — panel theme (map stays Protomaps default)",
                  "cloudy": "Cloudy — panel theme",
                  "night": "Night — panel theme"}
        self.statusBar().showMessage(labels.get(t, t), 5000)

    def _info(self, msg):
        QMessageBox.information(self, "Traffic Deployer", msg)

    def _warn(self, msg):
        QMessageBox.warning(self, "Traffic Deployer", msg)

    def closeEvent(self, event):
        try:
            self._hide_route_pick_dialog()
            for attr in ("_picocount_thread", "_route_thread", "_dl_thread", "_geocode_thread"):
                self._stop_worker(getattr(self, attr, None))
            if self.pages.currentIndex() == 2:
                self._flush_install_form()
            self._persist_shift(quiet=True)
            self._counter_resume_gps()
            self.gps.stop()
        except Exception:
            pass
        super().closeEvent(event)


def main():
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)
    crash_log.install_crash_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Traffic Deployer")
    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
