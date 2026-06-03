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
from PySide6.QtGui import QFont, QKeySequence, QShortcut
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
from core import connectivity, export, geo, ingest, offline_policy, setup_network, validate
from core.setup_checklist import evaluate as setup_checklist_eval
from core.setup_checklist import route_summary as build_route_summary
from core.field_ready import TOMORROW_STEPS, check_all
from core.offline_gate import evaluate as offline_gate_eval
from core.state import RouteState, ca_now
from ui.paths import (
    APP_DIR, COUNTER_DOWNLOAD_DIR, DATA_DIR, DEMO_CSV, DEMO_DIR, DEMO_EST, DIRECTIONS,
    UNDO_FIELDS, VENDOR_DIR, WEB_DIR,
)
from ui.route_pick_dialog import RoutePickOrderDialog
from ui.threads import (
    DownloadRoadsThread, GeocodeThread, PicocountThread, RouteOptimizeThread, SmokeTestThread,
)
from core import picocount
from ui.web_page import AppWebPage, ensure_qwebchannel_js
from ui import workflow as setup_workflow
from ui.pages import audit_page, pickup_page
from ui.setup_wizard import SetupWizard
from ui.widgets import WorkflowStrip, section_group, stat_card
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
        self.current_index = min(self.state.current_index, max(0, len(self.state.stops) - 1))
        self.pickup_index = self.state.pickup_index
        self.excel_paths = [p for p in self.state.excel_paths if os.path.isfile(p)]
        self._route_pick_mode = False
        self._route_pick_uids: list[str] = []
        self._route_pick_dialog: RoutePickOrderDialog | None = None
        self._picocount_thread = None
        self._counter_serial_grab_uid: str | None = None
        self.est_paths = [p for p in self.state.est_paths if os.path.isfile(p)]
        self.state.excel_paths = list(self.excel_paths)
        self.state.est_paths = list(self.est_paths)
        self._map_preview_stops: list[dict] = []
        self._map_preview_route: dict = {"polyline": [], "miles": 0.0, "graph": False}
        self.nav: dict = {"active": False}
        self._nav_thread = None
        self._undo_stack: list[dict] = []
        self._last_leg_push = 0.0
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self._autosave_current_stop)
        self._periodic_save = QTimer(self)
        self._periodic_save.timeout.connect(self._periodic_save_shift)
        self._periodic_save.start(45_000)
        self._map_health = QTimer(self)
        self._map_health.timeout.connect(self._map_health_check)
        self._map_health.start(20_000)

        ensure_qwebchannel_js()
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
        self.bridge.mapClicked.connect(lambda *_: None)
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
        self.gps_timer.start(1000)

        QTimer.singleShot(800, self._refresh_field_ready)
        QTimer.singleShot(900, self._refresh_map_preview)
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
        side.setMinimumWidth(420)
        side.setMaximumWidth(520)
        side.setAutoFillBackground(True)
        side.setAttribute(Qt.WA_StyledBackground, True)
        self._side_panel = side
        side_lay = QHBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.setSpacing(0)

        nav = QWidget()
        nav.setObjectName("navRail")
        nav.setFixedWidth(76)
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
        self.pages.addWidget(self._wrap_scroll(self._page_setup()))  # 0
        self.pages.addWidget(self._page_route())                     # 1
        self.pages.addWidget(self._wrap_scroll(self._page_install())) # 2
        self.pages.addWidget(pickup_page.build_pickup_page(self))     # 3
        self.pages.addWidget(audit_page.build_audit_page(self))      # 4
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
        self._splitter.setSizes([496, 824])
        body.addWidget(self._splitter, 1)

        wrap = QWidget()
        wrap.setLayout(body)
        root.addWidget(wrap, 1)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())
        self.status_gps = QLabel("GPS: searching...")
        self.status_route = QLabel("")
        self.statusBar().addWidget(self.status_gps)
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
        lay.setContentsMargins(16, 10, 16, 10)
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
        lay.addSpacing(16)

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
        lay.addWidget(theme_wrap)
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
        if self.pages.currentIndex() == 2 and i != 2:
            self._flush_install_form()
        self.pages.setCurrentIndex(i)
        for j in range(5):
            getattr(self, f"_navbtn_{j}").setChecked(j == i)
        if i == 0:
            self._refresh_workflow_strip()
        elif i == 1:
            self._refresh_route_list()
        elif i == 2:
            self._refresh_install()
        elif i == 3:
            self._refresh_pickup()
        elif i == 4:
            self._refresh_audit()
        self._update_right()

    def _update_right(self, force_map: bool = False):
        show_map = (
            force_map
            or self.nav.get("active")
            or bool(self.state.stops)
            or bool(getattr(self, "_map_preview_stops", None))
        )
        was_hidden = self.right_stack.currentIndex() == 0
        self.right_stack.setCurrentIndex(1 if show_map else 0)
        if show_map and (was_hidden or force_map) and self.state.stops:
            QTimer.singleShot(250, self._refresh_map_view)

    def _refresh_workflow_strip(self):
        if not hasattr(self, "workflow_strip"):
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

    # ---------------------------------------------------------- Setup page
    def _page_setup(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 12, 14, 14)
        v.setSpacing(10)

        self.workflow_strip = WorkflowStrip()
        v.addWidget(self.workflow_strip)

        sec_profile = section_group("Profile & save", v)
        self.txt_profile = QLineEdit(self.state.profile)
        self.txt_profile.setPlaceholderText("e.g. DEFAULT, WEEK9")
        sec_profile.addWidget(self.txt_profile)
        row_prof = QHBoxLayout()
        b_prof = QPushButton("Load / switch")
        b_prof.setObjectName("secondary")
        b_prof.clicked.connect(self._switch_profile)
        b_save_as = QPushButton("Save as new")
        b_save_as.setObjectName("secondary")
        b_save_as.clicked.connect(self._save_profile_as)
        row_prof.addWidget(b_prof)
        row_prof.addWidget(b_save_as)
        sec_profile.addLayout(row_prof)
        b_save_now = QPushButton("Save progress now")
        b_save_now.setObjectName("secondary")
        b_save_now.clicked.connect(self._save_shift_now)
        sec_profile.addWidget(b_save_now)
        self.lbl_save_hint = QLabel("Auto-saves every ~45s. Re-build keeps install data.")
        self.lbl_save_hint.setObjectName("hint")
        self.lbl_save_hint.setWordWrap(True)
        sec_profile.addWidget(self.lbl_save_hint)

        sec_ready = section_group("Field readiness", v)
        self.lbl_field_score = QLabel("")
        self.lbl_field_score.setStyleSheet("font-weight:800;font-size:15px;")
        sec_ready.addWidget(self.lbl_field_score)
        self.lbl_field_checks = QLabel("")
        self.lbl_field_checks.setWordWrap(True)
        self.lbl_field_checks.setStyleSheet("font-size:12px;line-height:1.35;")
        sec_ready.addWidget(self.lbl_field_checks)
        row_ready = QHBoxLayout()
        b_refresh_ready = QPushButton("Refresh")
        b_refresh_ready.setObjectName("secondary")
        b_refresh_ready.clicked.connect(self._refresh_field_ready)
        b_smoke = QPushButton("Smoke test")
        b_smoke.setObjectName("secondary")
        b_smoke.clicked.connect(self._run_smoke_test)
        row_ready.addWidget(b_refresh_ready)
        row_ready.addWidget(b_smoke)
        sec_ready.addLayout(row_ready)
        row_setup_tools = QHBoxLayout()
        b_checklist = QPushButton("Setup checklist")
        b_checklist.setObjectName("secondary")
        b_checklist.clicked.connect(self._show_setup_checklist)
        b_net = QPushButton("Test home Wi‑Fi")
        b_net.setObjectName("secondary")
        b_net.clicked.connect(self._run_setup_network_test)
        row_setup_tools.addWidget(b_checklist)
        row_setup_tools.addWidget(b_net)
        b_wiz = QPushButton("Quick setup wizard")
        b_wiz.setObjectName("secondary")
        b_wiz.clicked.connect(self._show_setup_wizard)
        row_setup_tools.addWidget(b_wiz)
        sec_ready.addLayout(row_setup_tools)

        sec_origin = section_group("1 — Starting point", v)
        self.lbl_origin = QLabel("")
        sec_origin.addWidget(self.lbl_origin)
        b_usb = QPushButton("Read USB GPS")
        b_usb.clicked.connect(self._origin_from_gps)
        sec_origin.addWidget(b_usb)
        self.txt_address = QLineEdit()
        self.txt_address.setPlaceholderText("e.g. 123 Main St, Garden Grove, CA 92840")
        self.txt_address.returnPressed.connect(self._origin_from_address)
        sec_origin.addWidget(self.txt_address)
        b_addr = QPushButton("Search address (online)")
        b_addr.clicked.connect(self._origin_from_address)
        self.btn_address = b_addr
        sec_origin.addWidget(b_addr)
        self.lbl_address_hint = QLabel("")
        self.lbl_address_hint.setObjectName("hint")
        self.lbl_address_hint.setWordWrap(True)
        sec_origin.addWidget(self.lbl_address_hint)
        row = QHBoxLayout()
        self.spin_lat = QDoubleSpinBox()
        self.spin_lat.setDecimals(5)
        self.spin_lat.setRange(-90, 90)
        self.spin_lat.setValue(self.state.home[0])
        self.spin_lon = QDoubleSpinBox()
        self.spin_lon.setDecimals(5)
        self.spin_lon.setRange(-180, 180)
        self.spin_lon.setValue(self.state.home[1])
        row.addWidget(self.spin_lat)
        row.addWidget(self.spin_lon)
        sec_origin.addLayout(row)
        b_coords = QPushButton("Save coordinates")
        b_coords.setObjectName("secondary")
        b_coords.clicked.connect(self._origin_from_coords)
        sec_origin.addWidget(b_coords)
        b_default = QPushButton("Save as DEFAULT start")
        b_default.setObjectName("primary")
        b_default.clicked.connect(self._save_default_home)
        sec_origin.addWidget(b_default)
        b_load_def = QPushButton("Load DEFAULT start")
        b_load_def.setObjectName("secondary")
        b_load_def.clicked.connect(self._load_default_home)
        sec_origin.addWidget(b_load_def)
        self.btn_saved_home = QPushButton("Use saved home address")
        self.btn_saved_home.setObjectName("secondary")
        self.btn_saved_home.clicked.connect(self._use_saved_home)
        sec_origin.addWidget(self.btn_saved_home)

        sec_files = section_group("2 — Field files", v)
        b_excel = QPushButton("Add Excel / CSV")
        b_excel.clicked.connect(self._pick_excel)
        sec_files.addWidget(b_excel)
        self.list_excel = QListWidget()
        self.list_excel.setMaximumHeight(64)
        sec_files.addWidget(self.list_excel)
        b_est = QPushButton("Add .EST map(s)")
        b_est.clicked.connect(self._pick_est)
        sec_files.addWidget(b_est)
        self.list_est = QListWidget()
        self.list_est.setMaximumHeight(72)
        sec_files.addWidget(self.list_est)
        row_files = QHBoxLayout()
        b_clear = QPushButton("Clear lists")
        b_clear.setObjectName("secondary")
        b_clear.clicked.connect(self._clear_files)
        b_demo = QPushButton("Demo files")
        b_demo.setObjectName("secondary")
        b_demo.clicked.connect(self._load_demo_files)
        row_files.addWidget(b_clear)
        row_files.addWidget(b_demo)
        sec_files.addLayout(row_files)

        sec_build = section_group("3 — Road map & route", v)
        b_roads = QPushButton("Download road map (online)")
        b_roads.clicked.connect(self._download_roads)
        self.btn_download_roads = b_roads
        sec_build.addWidget(b_roads)
        b_import_roads = QPushButton("Import road map (.graphml)")
        b_import_roads.setObjectName("secondary")
        b_import_roads.clicked.connect(self._import_roads)
        self.btn_import_roads = b_import_roads
        sec_build.addWidget(b_import_roads)
        self.lbl_roads_hint = QLabel(
            "Work Wi‑Fi may block download — import road_graph.graphml from home PC.")
        self.lbl_roads_hint.setObjectName("hint")
        self.lbl_roads_hint.setWordWrap(True)
        sec_build.addWidget(self.lbl_roads_hint)
        self.btn_build = QPushButton("PLAN ROUTE — pick stop order")
        self.btn_build.setObjectName("primary")
        self.btn_build.clicked.connect(self._build_route_from_uploads)
        sec_build.addWidget(self.btn_build)

        sec_gps = section_group("4 — Before you leave (field mode)", v)
        self.combo_port = QComboBox()
        sec_gps.addWidget(self.combo_port)
        rowg = QHBoxLayout()
        b_refresh_ports = QPushButton("Ports")
        b_refresh_ports.setObjectName("secondary")
        b_refresh_ports.clicked.connect(self._refresh_ports)
        b_useport = QPushButton("Use port")
        b_useport.setObjectName("secondary")
        b_useport.clicked.connect(self._set_gps_port)
        rowg.addWidget(b_refresh_ports)
        rowg.addWidget(b_useport)
        sec_gps.addLayout(rowg)
        self._refresh_ports()
        self.lbl_offline = QLabel("")
        self.lbl_offline.setWordWrap(True)
        sec_gps.addWidget(self.lbl_offline)
        hint_mode = QLabel("Use I'm online / Go offline in the top bar before you leave or when back home.")
        hint_mode.setObjectName("hint")
        hint_mode.setWordWrap(True)
        sec_gps.addWidget(hint_mode)

        v.addStretch(1)
        return w

    def _refresh_field_ready(self):
        if not hasattr(self, "lbl_field_score"):
            return
        gps_snap = self.gps.latest() if hasattr(self, "gps") else None
        r = check_all(
            APP_DIR,
            probe_gps=gps_snap is None,
            gps_snapshot=gps_snap,
            stop_server_after=False,
        )
        score = r["score"]
        if score >= 88:
            color, tag = "#15803d", "READY FOR FIELD"
        elif score >= 70:
            color, tag = "#b45309", "READY WITH WARNINGS"
        else:
            color, tag = "#b91c1c", "FIX BEFORE FIELD"
        self.lbl_field_score.setText(f"{tag} — {score}/100")
        self.lbl_field_score.setStyleSheet(f"font-weight:800;font-size:15px;color:{color};")
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
            "Run setup_maps.py on WiFi if the offline map is missing.",
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

    # ---------------------------------------------------------- Route page
    def _page_route(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 12, 14, 14)
        v.setSpacing(10)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(8)
        card_stops, self.lbl_stat_stops = stat_card("Stops", "0")
        card_miles, self.lbl_stat_miles = stat_card("Miles", "—")
        card_kind, self.lbl_stat_kind = stat_card("Routing", "—")
        stats_row.addWidget(card_stops, 1)
        stats_row.addWidget(card_miles, 1)
        stats_row.addWidget(card_kind, 1)
        v.addLayout(stats_row)
        self.lbl_route_stats = QLabel("")
        self.lbl_route_stats.hide()
        self.lbl_route_summary = QLabel("")
        self.lbl_route_summary.setObjectName("hint")
        self.lbl_route_summary.setWordWrap(True)
        self.lbl_route_summary.setStyleSheet("font-weight:700;font-size:13px;color:#0f2744;")
        v.addWidget(self.lbl_route_summary)
        self.lbl_field_strip = QLabel("")
        self.lbl_field_strip.setStyleSheet("font-size:12px;color:#475569;")
        v.addWidget(self.lbl_field_strip)

        self.lbl_drive_banner = QLabel("")
        self.lbl_drive_banner.setWordWrap(True)
        self.lbl_drive_banner.setStyleSheet(
            "background:#e3f2fd;border:1px solid #90caf9;border-radius:8px;"
            "padding:10px;font-weight:700;font-size:13px;color:#0d47a1;")
        self.lbl_drive_banner.hide()
        v.addWidget(self.lbl_drive_banner)

        sec_drive = section_group("Drive", v)
        self.btn_start = QPushButton("START DRIVING")
        self.btn_start.setObjectName("go")
        self.btn_start.clicked.connect(self._toggle_drive)
        sec_drive.addWidget(self.btn_start)
        hint_drive = QLabel("Follow Me on the map. The next stop number pulses so you know where to head.")
        hint_drive.setObjectName("hint")
        hint_drive.setWordWrap(True)
        sec_drive.addWidget(hint_drive)

        sec_pick = section_group("Plan route (pick order)", v)
        self.lbl_pick_status = QLabel(
            "Choose stop 1, 2, 3… from the dropdown or map. A Route order window lists "
            "picks as you go — drag or Up/Down to fix order.")
        self.lbl_pick_status.setObjectName("hint")
        self.lbl_pick_status.setWordWrap(True)
        sec_pick.addWidget(self.lbl_pick_status)
        row_pick_site = QHBoxLayout()
        self.lbl_pick_slot = QLabel("Stop 1:")
        self.lbl_pick_slot.setMinimumWidth(52)
        self.combo_pick_site = QComboBox()
        self.combo_pick_site.setMinimumWidth(220)
        self.combo_pick_site.activated.connect(self._on_pick_combo_chosen)
        row_pick_site.addWidget(self.lbl_pick_slot)
        row_pick_site.addWidget(self.combo_pick_site, 1)
        sec_pick.addLayout(row_pick_site)
        row_pick = QHBoxLayout()
        self.btn_pick_auto = QPushButton("Auto-finish rest")
        self.btn_pick_auto.setObjectName("secondary")
        self.btn_pick_auto.clicked.connect(self._route_pick_auto_finish)
        self.btn_pick_clear = QPushButton("Clear picks")
        self.btn_pick_clear.setObjectName("secondary")
        self.btn_pick_clear.clicked.connect(self._route_pick_clear)
        self.btn_pick_apply = QPushButton("Apply route")
        self.btn_pick_apply.setObjectName("primary")
        self.btn_pick_apply.clicked.connect(self._route_pick_apply)
        row_pick.addWidget(self.btn_pick_auto)
        row_pick.addWidget(self.btn_pick_clear)
        row_pick.addWidget(self.btn_pick_apply)
        sec_pick.addLayout(row_pick)
        self.btn_pick_order_win = QPushButton("Show route order window")
        self.btn_pick_order_win.setObjectName("secondary")
        self.btn_pick_order_win.clicked.connect(self._show_route_pick_dialog)
        sec_pick.addWidget(self.btn_pick_order_win)

        sec_map = section_group("Map", v)
        self.chk_show_segments = QCheckBox("Work-site lines (follow streets)")
        self.chk_show_segments.setChecked(True)
        self.chk_show_segments.stateChanged.connect(lambda: self._push_state())
        sec_map.addWidget(self.chk_show_segments)
        row_day = QHBoxLayout()
        row_day.addWidget(QLabel("Map filter:"))
        self.combo_day = QComboBox()
        self.combo_day.currentTextChanged.connect(self._on_day_filter_changed)
        row_day.addWidget(self.combo_day, 1)
        sec_map.addLayout(row_day)
        b_fit = QPushButton("Zoom to all stops")
        b_fit.setObjectName("secondary")
        b_fit.clicked.connect(lambda: self._push_state(fit=True))
        sec_map.addWidget(b_fit)
        b_recover = QPushButton("Recover map (blank canvas)")
        b_recover.setObjectName("secondary")
        b_recover.clicked.connect(self._recover_map)
        sec_map.addWidget(b_recover)

        sec_stops = section_group("Stop list", v, stretch=1)
        self.list_route = QListWidget()
        self.list_route.itemClicked.connect(self._route_item_clicked)
        sec_stops.addWidget(self.list_route, 1)

        row_nudge = QHBoxLayout()
        b_up = QPushButton("Move stop up")
        b_up.setObjectName("secondary")
        b_up.clicked.connect(lambda: self._nudge_stop(-1))
        b_dn = QPushButton("Move stop down")
        b_dn.setObjectName("secondary")
        b_dn.clicked.connect(lambda: self._nudge_stop(1))
        b_retrace = QPushButton("Re-trace route only")
        b_retrace.setObjectName("secondary")
        b_retrace.clicked.connect(self._retrace_route_only)
        row_nudge.addWidget(b_up)
        row_nudge.addWidget(b_dn)
        row_nudge.addWidget(b_retrace)
        v.addLayout(row_nudge)
        row_actions = QHBoxLayout()
        b_reopt = QPushButton("Re-optimize")
        b_reopt.setObjectName("secondary")
        b_reopt.clicked.connect(self._reoptimize)
        b_reset = QPushButton("Clear shift…")
        b_reset.setObjectName("secondary")
        b_reset.clicked.connect(self._reset_route)
        row_actions.addWidget(b_reopt)
        row_actions.addWidget(b_reset)
        v.addLayout(row_actions)
        return w

    # -------------------------------------------------------- Install page
    def _page_install(self) -> QWidget:
        w = QWidget()
        w.setObjectName("installPage")
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)

        header = QFrame()
        header.setObjectName("installHeader")
        hv = QVBoxLayout(header)
        hv.setContentsMargins(14, 12, 14, 12)
        hv.setSpacing(4)
        self.lbl_install_title = QLabel("No stop selected.")
        self.lbl_install_title.setObjectName("installTitle")
        self.lbl_install_title.setWordWrap(True)
        hv.addWidget(self.lbl_install_title)
        self.lbl_install_prog = QLabel("")
        self.lbl_install_prog.setObjectName("installSub")
        hv.addWidget(self.lbl_install_prog)
        self.lbl_cross_hint = QLabel("")
        self.lbl_cross_hint.setObjectName("hint")
        self.lbl_cross_hint.setWordWrap(True)
        hv.addWidget(self.lbl_cross_hint)
        v.addWidget(header)

        sec_warn = section_group("Alerts", v)
        self.lbl_street_warn = QLabel("")
        self.lbl_street_warn.setObjectName("installWarn")
        self.lbl_street_warn.setWordWrap(True)
        sec_warn.addWidget(self.lbl_street_warn)

        sec_compass = section_group("Compass (when stopped)", v)
        self.lbl_compass = QLabel("Waiting for GPS heading…")
        self.lbl_compass.setObjectName("installCompass")
        sec_compass.addWidget(self.lbl_compass)
        self.lbl_compass_sub = QLabel("")
        self.lbl_compass_sub.setObjectName("hint")
        self.lbl_compass_sub.setWordWrap(True)
        sec_compass.addWidget(self.lbl_compass_sub)
        b_comp_dir = QPushButton("Set direction from compass")
        b_comp_dir.setObjectName("secondary")
        b_comp_dir.clicked.connect(self._set_dir_from_compass)
        sec_compass.addWidget(b_comp_dir)

        sec_counter = section_group("PicoCount 2500 (USB)", v)
        row_cp = QHBoxLayout()
        row_cp.addWidget(QLabel("Port"))
        self.combo_counter_port = QComboBox()
        self.combo_counter_port.setMinimumWidth(88)
        row_cp.addWidget(self.combo_counter_port, 1)
        b_counter_ports = QPushButton("Refresh")
        b_counter_ports.setObjectName("secondary")
        b_counter_ports.clicked.connect(self._counter_refresh_ports)
        row_cp.addWidget(b_counter_ports)
        sec_counter.addLayout(row_cp)
        self.lbl_counter_status = QLabel("Plug in download cable, then Connect.")
        self.lbl_counter_status.setObjectName("hint")
        self.lbl_counter_status.setWordWrap(True)
        sec_counter.addWidget(self.lbl_counter_status)
        self.lbl_counter_unit = QLabel("")
        self.lbl_counter_unit.setObjectName("hint")
        self.lbl_counter_unit.setWordWrap(True)
        sec_counter.addWidget(self.lbl_counter_unit)
        row_cbtn = QHBoxLayout()
        self.btn_counter_connect = QPushButton("Connect")
        self.btn_counter_connect.setObjectName("secondary")
        self.btn_counter_connect.clicked.connect(self._counter_connect)
        self.btn_counter_read_serial = QPushButton("Read serial")
        self.btn_counter_read_serial.setObjectName("secondary")
        self.btn_counter_read_serial.clicked.connect(
            lambda: self._counter_read_serial(auto=False))
        self.btn_counter_clear = QPushButton("Clear & set ID")
        self.btn_counter_clear.setObjectName("primary")
        self.btn_counter_clear.clicked.connect(self._counter_clear_configure)
        row_cbtn.addWidget(self.btn_counter_connect)
        row_cbtn.addWidget(self.btn_counter_read_serial)
        row_cbtn.addWidget(self.btn_counter_clear)
        sec_counter.addLayout(row_cbtn)
        self._counter_refresh_ports()

        sec_form = section_group("Install capture", v)
        sec_form.addWidget(self._h("STREET NAME"))
        self.txt_street = QLineEdit()
        self.txt_street.textChanged.connect(self._schedule_autosave)
        sec_form.addWidget(self.txt_street)
        row = QHBoxLayout()
        self.combo_dir = QComboBox()
        self.combo_dir.addItems(DIRECTIONS)
        self.combo_dir.currentTextChanged.connect(self._on_install_dir_changed)
        self.spin_lanes = QSpinBox()
        self.spin_lanes.setRange(1, 20)
        self.spin_lanes.setValue(2)
        self.spin_lanes.valueChanged.connect(lambda *_: self._schedule_autosave())
        self.txt_serial = QLineEdit()
        self.txt_serial.setPlaceholderText("Serial #")
        self.txt_serial.textChanged.connect(self._schedule_autosave)
        row.addWidget(QLabel("Dir"))
        row.addWidget(self.combo_dir, 1)
        row.addWidget(QLabel("Lanes"))
        row.addWidget(self.spin_lanes)
        sec_form.addLayout(row)
        sec_form.addWidget(self._h("SERIAL"))
        sec_form.addWidget(self.txt_serial)
        sec_form.addWidget(self._h("FIELD NOTES"))
        self.txt_notes = QPlainTextEdit()
        self.txt_notes.setMaximumHeight(72)
        self.txt_notes.textChanged.connect(self._schedule_autosave)
        sec_form.addWidget(self.txt_notes)
        b_grab = QPushButton("Grab GPS Here (precise)")
        b_grab.setObjectName("secondary")
        b_grab.clicked.connect(self._grab_gps_here)
        sec_form.addWidget(b_grab)
        self.lbl_grab = QLabel("")
        self.lbl_grab.setObjectName("hint")
        sec_form.addWidget(self.lbl_grab)
        row_photo = QHBoxLayout()
        b_photo = QPushButton("Attach photo")
        b_photo.setObjectName("secondary")
        b_photo.clicked.connect(self._attach_install_photo)
        b_clear_photo = QPushButton("Clear")
        b_clear_photo.setObjectName("secondary")
        b_clear_photo.clicked.connect(self._clear_install_photo)
        row_photo.addWidget(b_photo)
        row_photo.addWidget(b_clear_photo)
        sec_form.addLayout(row_photo)
        self.lbl_install_photo = QLabel("")
        self.lbl_install_photo.setObjectName("hint")
        self.lbl_install_photo.setWordWrap(True)
        sec_form.addWidget(self.lbl_install_photo)

        row2 = QHBoxLayout()
        b_install = QPushButton("INSTALL  (I)")
        b_install.setObjectName("fieldPrimary")
        b_install.clicked.connect(lambda: self._commit_install(True))
        b_skip = QPushButton("SKIP  (S)")
        b_skip.setObjectName("fieldSkip")
        b_skip.clicked.connect(lambda: self._commit_install(False))
        row2.addWidget(b_install, 2)
        row2.addWidget(b_skip, 1)
        v.addLayout(row2)
        self.btn_undo_install = QPushButton("Undo last action  (Ctrl+Z)")
        self.btn_undo_install.setObjectName("secondary")
        self.btn_undo_install.setEnabled(False)
        self.btn_undo_install.clicked.connect(self._undo_last_action)
        v.addWidget(self.btn_undo_install)
        lbl_keys = QLabel("I install · S skip · G grab GPS · N/P prev/next")
        lbl_keys.setObjectName("hint")
        lbl_keys.setWordWrap(True)
        v.addWidget(lbl_keys)
        b_show = QPushButton("Show on map")
        b_show.setObjectName("secondary")
        b_show.clicked.connect(self._center_current)
        v.addWidget(b_show)
        v.addStretch(1)
        row3 = QHBoxLayout()
        b_prev = QPushButton("← Prev")
        b_prev.setObjectName("secondary")
        b_prev.clicked.connect(lambda: self._nav_install(-1))
        b_next = QPushButton("Next →")
        b_next.setObjectName("secondary")
        b_next.clicked.connect(lambda: self._nav_install(1))
        row3.addWidget(b_prev)
        row3.addWidget(b_next)
        v.addLayout(row3)
        return w

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
            self._refresh_map_view()

    def _refresh_map_view(self):
        """Resize the WebEngine canvas (it starts at 0px while hidden) and redraw."""
        self.bridge.refresh_view()
        self._push_state(fit=True)

    def _display_route(self) -> dict:
        if self.nav.get("active"):
            leg = self.nav.get("leg_poly") or []
            return {"polyline": leg, "miles": self.nav.get("leg_miles", 0.0),
                    "graph": self.nav.get("graph", False)}
        return self.state.route

    def _compute_leg_poly(self, a: tuple, b: tuple) -> list[list[float]]:
        if road_router.has_graph(DATA_DIR):
            try:
                g = road_router.load_graph(DATA_DIR)
                leg = road_router.route_between(g, a, b)
                if leg.get("polyline"):
                    return [[float(p[0]), float(p[1])] for p in leg["polyline"]]
            except Exception:
                pass
        return [[float(a[0]), float(a[1])], [float(b[0]), float(b[1])]]

    @staticmethod
    def _trim_poly_ahead(poly: list, lat: float, lon: float) -> list:
        if not poly or len(poly) < 2:
            return poly
        best_i, best_d = 0, 1e18
        for i, p in enumerate(poly):
            d = MainWindow._dist_m(lat, lon, p[0], p[1])
            if d < best_d:
                best_d, best_i = d, i
        trimmed = [[lat, lon]] + poly[best_i + 1:]
        return trimmed if len(trimmed) >= 2 else poly[-2:]

    def _drive_start_point(self) -> tuple[float, float]:
        g = self.gps.latest()
        if g.get("fix") and g.get("lat") is not None:
            return float(g["lat"]), float(g["lon"])
        return tuple(self.state.home)

    def _remaining_drive_stops(self) -> list[dict]:
        return [s for s in self.nav.get("stops", self.state.stops)
                if not s.get("installed") and not s.get("skipped")]

    def _set_nav_leg(
        self,
        from_pt: tuple[float, float],
        target: dict,
        *,
        push_map: bool = True,
        to_pt: tuple[float, float] | None = None,
    ):
        if to_pt is None:
            to_pt = self.state.point(target)
        leg = self._compute_leg_poly(from_pt, to_pt)
        self.nav["leg_poly"] = leg
        self.nav["leg_miles"] = self._dist_m(from_pt[0], from_pt[1], to_pt[0], to_pt[1]) / 1609.34
        self.nav["maneuvers"] = []
        self.nav["step"] = 0
        if road_router.has_graph(DATA_DIR):
            try:
                g = road_router.load_graph(DATA_DIR)
                plan = road_router.leg_plan(g, from_pt, to_pt, stop_index=0)
                self.nav["maneuvers"] = plan.get("maneuvers") or []
            except Exception:
                pass
        self._update_drive_banner(from_pt, to_pt, target)
        if push_map:
            self._push_state()

    def _update_drive_banner(
        self,
        from_pt: tuple[float, float],
        to_pt: tuple[float, float],
        target: dict | None = None,
    ):
        if not hasattr(self, "lbl_drive_banner"):
            return
        if not self.nav.get("active"):
            self.lbl_drive_banner.hide()
            return
        maneuvers = self.nav.get("maneuvers") or []
        step = int(self.nav.get("step", 0))
        if self.nav.get("phase") == "home":
            d = self._dist_m(from_pt[0], from_pt[1], to_pt[0], to_pt[1]) / 1609.34
            self.lbl_drive_banner.setText(f"Return to start — {d:.1f} mi")
        elif target:
            tid = target.get("id", "")
            st = self._street_label(target)
            if step < len(maneuvers):
                m = maneuvers[step]
                mt = str(m.get("type", "straight")).replace("_", " ").title()
                street = str(m.get("street", "") or "").strip()
                extra = f" on {street}" if street else ""
                self.lbl_drive_banner.setText(f"Site {tid} — {mt}{extra}  ({st})")
            else:
                d = self._dist_m(from_pt[0], from_pt[1], to_pt[0], to_pt[1]) / 1609.34
                self.lbl_drive_banner.setText(f"Site {tid} — {d:.1f} mi  ({st})")
        else:
            self.lbl_drive_banner.setText("Driving…")
        self.lbl_drive_banner.show()

    def _refresh_drive_leg_trim(self, lat: float, lon: float):
        """Driving highlights next stop on map only (no blue trace)."""
        self._push_state()

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
        return f"Select site {n + 1} of {total}"

    def _ask_route_build_mode(self) -> str | None:
        box = QMessageBox(self)
        box.setWindowTitle("Build route")
        box.setText("How should stop order be chosen?")
        box.setInformativeText(
            "Pick route: dropdown or map for stop 1, 2, 3…; Apply auto-fills any left.\n"
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
            from core.map_display import enrich_segment_paths

            self._map_preview_stops = routing.assign_crossings_for_display(
                raw, self.state.home, DATA_DIR)
            enrich_segment_paths(self._map_preview_stops, DATA_DIR)
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
        driving = bool(self.nav.get("active"))
        preview = bool(self._map_preview_stops) and not self.state.stops
        picking = bool(self._route_pick_mode)
        if picking:
            mode = "pick"
        elif driving:
            mode = "drive"
        elif preview:
            mode = "preview"
        else:
            mode = "plan"
        hi = self._highlight_stop_uid()
        st = {
            "theme": self.state.theme,
            "home": list(self.state.home),
            "stops": self._stops_for_map(),
            "route": {"polyline": [], "graph": False},
            "fit": fit,
            "driving": driving,
            "map_mode": mode,
            "highlight_uid": hi,
            "drive_target_uid": hi if driving else None,
            "pick_order": list(self._route_pick_uids) if picking else [],
            "pick_prompt": self._pick_prompt_text() if picking else "",
            "pick_letters": self._pick_site_letters() if picking else {},
            "show_segments": self.chk_show_segments.isChecked(),
            "show_badges": not picking,
        }
        self.bridge.send_state(st)
        miles = self.state.route.get("miles", 0.0)
        drive = (miles / 30.0) * 60 if miles else 0
        self.status_route.setText(f"Stops: {len(self.state.stops)}   Route: {miles:.1f} mi   ~{drive:.0f} min")

    def _on_stop_clicked(self, uid: str):
        if self._route_pick_mode:
            self._route_pick_add(uid)
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
            self.bridge.send_gps({
                "lat": lat, "lon": lon, "heading": hdg,
                "heading_mode": g.get("heading_mode"), "speed_mps": g.get("speed_mps"),
            })
            self._update_compass_labels(g)
            self.status_gps.setText(f"GPS: FIX  {g.get('satellites', 0)} sats   {lat:.5f}, {lon:.5f}")
            if self.nav.get("active"):
                self._drive_update(lat, lon)
            if hasattr(self, "lbl_field_score") and not hasattr(self, "_gps_ready_refreshed"):
                self._gps_ready_refreshed = True
                self._refresh_field_ready()
            self._refresh_field_strip_ui()
        elif g.get("connected"):
            self.status_gps.setText(f"GPS: searching... {g.get('satellites', 0)} sats (need clear sky)")
            self._refresh_field_strip_ui()
        else:
            self.status_gps.setText("GPS: not detected (check USB receiver)")
            self._refresh_field_strip_ui()

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
        if hdg is None:
            txt = "Compass: no heading yet — drive a short distance, then stop."
            sub = ""
        else:
            card = self._heading_cardinal(hdg)
            txt = f"Facing: {hdg:.0f}° ({card})"
            if mode == "locked":
                sub = "Stopped — locked heading (use for install direction)"
            elif mode == "moving":
                sub = "Moving — live GPS course"
            else:
                sub = "Slow/stop — averaging recent heading"
        if hasattr(self, "lbl_compass"):
            self.lbl_compass.setText(txt)
        if hasattr(self, "lbl_compass_sub"):
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
        self.nav = {"active": False}
        self._undo_stack.clear()
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
        lat, lon = self.spin_lat.value(), self.spin_lon.value()
        self.state.save_default_home(lat, lon)
        self._refresh_origin_label()
        self._refresh_workflow_strip()
        self._push_state()
        self.statusBar().showMessage(f"Default start saved: {lat:.5f}, {lon:.5f}", 6000)

    def _load_default_home(self):
        if not self.state.default_home:
            self._warn("No default start saved yet. Enter GPS coords and press Save as DEFAULT start.")
            return
        self.state.apply_default_home()
        self.spin_lat.setValue(self.state.home[0])
        self.spin_lon.setValue(self.state.home[1])
        self._refresh_origin_label()
        self._refresh_workflow_strip()
        self.state.save()
        self._push_state(fit=True)
        self.statusBar().showMessage("Loaded saved default start.", 4000)

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
            self._warn("No saved home yet.\n\nSearch an address or save DEFAULT start first.")
            return
        lat, lon = self.state.saved_home_coords
        label = self.state.saved_home_label or f"{lat:.5f}, {lon:.5f}"
        self._set_origin(lat, lon, f"Restored home:\n{label[:120]}")

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
            self.btn_saved_home.setEnabled(True)
            self.btn_saved_home.setText(
                f"Use saved home ({self.state.saved_home_label[:40]}…)"
                if has and len(self.state.saved_home_label) > 40
                else (f"Use saved home — {self.state.saved_home_label[:50]}" if has else "Use saved home address")
            )

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

    def _refresh_online_status(self):
        """Geocode reachability hint when online (does not overwrite route status bar)."""
        if not self._internet_allowed():
            return
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
                "Address search unavailable — run via START.bat (needs requests package).")
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
            if healthy:
                return
            self.bridge.refresh_view()
            self._push_state(fit=False)
            self.statusBar().showMessage("Map refreshed (recovered blank canvas).", 5000)

        n = len(self._stops_for_map())
        self.view.page().runJavaScript(
            f"!!window.__mapLoaded && window.__dbg.lastStops >= {n} && window.__dbg.applied > 0",
            cb)

    def _autosave_current_stop(self):
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return
        self._flush_install_form()
        self._persist_shift("Saved locally.", quiet=False)

    def _set_origin(self, lat, lon, note=""):
        self.state.home = (float(lat), float(lon))
        self.state.save()
        self._refresh_origin_label()
        self._refresh_workflow_strip()
        self.spin_lat.setValue(lat); self.spin_lon.setValue(lon)
        self.bridge.fly_to(lat, lon, 13)
        self._push_state()
        if note:
            self._info(note)

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
        if g.get("fix"):
            self._set_origin(g["lat"], g["lon"], "Origin set from USB GPS.")
            return
        lat, lon = gps_reader.get_fix()
        if lat is not None:
            self._set_origin(lat, lon, "Origin set from USB GPS.")
        else:
            self._warn("No GPS fix yet. Give the receiver a clear view of the sky.")

    def _origin_from_address(self):
        if not self._internet_allowed():
            self._field_notice(
                "Field mode — address search is off. Use GPS or coordinates; "
                "Tap I'm online at home for address search.")
            return
        if not geo.geocode_available():
            self._warn(
                "Address search needs the 'requests' library.\n\n"
                "Launch with START.bat so the venv is active.")
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
                self._warn("Address search unavailable — run START.bat.")
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
            self.state.save_home_address(c["lat"], c["lon"], c["label"])
            self._set_origin(c["lat"], c["lon"], f"Origin set:\n{c['label'][:120]}")
            self._refresh_field_strip_ui()
            return
        labels = [c["label"][:120] for c in cands]
        pick, ok = QInputDialog.getItem(
            self, "Pick your address", "Several matches — choose one:", labels, 0, False)
        if not ok or not pick:
            self.statusBar().showMessage("Address search cancelled.", 4000)
            return
        idx = labels.index(pick)
        c = cands[idx]
        self.state.save_home_address(c["lat"], c["lon"], c["label"])
        self._set_origin(c["lat"], c["lon"], f"Origin set:\n{c['label'][:120]}")
        self._refresh_field_strip_ui()

    def _origin_from_coords(self):
        self._set_origin(self.spin_lat.value(), self.spin_lon.value(), "Origin saved.")
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

    def _download_roads(self):
        if not self._internet_allowed():
            self._warn(
                "Field (offline) mode — download needs Wi‑Fi at home.\n\n"
                "Use Import road map if you copied road_graph.graphml, or "
                "Tap I'm online on home Wi‑Fi.")
            return
        if not road_router.HAS_ROUTING:
            self._warn("Routing libraries (osmnx) are not installed.")
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
                    "Now press BUILD OPTIMIZED ROUTE.")
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
                "Now press BUILD OPTIMIZED ROUTE.")
        elif road_router.has_graph(DATA_DIR):
            g = road_router.load_graph(DATA_DIR)
            n = len(g.nodes) if g else 0
            self._info(f"Road map imported and loaded ({n:,} nodes).\nNow press BUILD OPTIMIZED ROUTE.")
        else:
            mb = info.get("size_mb", "?")
            self._warn(
                f"File copied ({mb} MB) but graph did not load.\n\n"
                "Launch via START.bat (.venv) or re-copy road_graph.graphml from home PC."
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
            self._route_pick_dialog = dlg
        return self._route_pick_dialog

    def _show_route_pick_dialog(self) -> None:
        dlg = self._ensure_route_pick_dialog()
        if not dlg.isVisible():
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

    def _hide_route_pick_dialog(self) -> None:
        if self._route_pick_dialog is not None:
            self._route_pick_dialog.hide()

    def _route_pick_set_order(self, uids: list[str]) -> None:
        if not self._route_pick_mode:
            return
        by_uid = {s["uid"]: s for s in self.state.stops}
        self._route_pick_uids = [u for u in uids if u in by_uid]
        self._refresh_route_pick_ui(sync_dialog=False)
        self._refresh_route_list()
        self._push_state()

    def _begin_route_pick(self, stops: list[dict]) -> None:
        if not road_router.has_graph(DATA_DIR):
            msg = (
                "Download the road map first (Setup → Download road map).\n\n"
                "Work-site lines need the road graph to trace streets.")
            if self.state.offline_mode:
                self._field_notice(
                    "No local road map — import road_graph.graphml at home, or resume online mode.")
            else:
                self._warn(msg)
            return
        from core.map_display import enrich_segment_paths

        self._route_pick_mode = True
        self._route_pick_uids = []
        self.state.stops = list(stops)
        self.state.route = {"polyline": [], "miles": 0.0, "graph": False}
        enrich_segment_paths(self.state.stops, DATA_DIR)
        self._go_page(1)
        self._refresh_route_pick_ui()
        self._show_route_pick_dialog()
        self._refresh_route_list()
        self._push_state(fit=True)
        self.statusBar().showMessage(
            f"Pick route: {self._pick_prompt_text()} — map, dropdown, or Route order window.", 12000)

    def _refresh_route_pick_ui(self, *, sync_dialog: bool = True) -> None:
        if not hasattr(self, "lbl_pick_status"):
            return
        n = len(self._route_pick_uids)
        total = len(self.state.stops)
        on = self._route_pick_mode
        self.btn_pick_apply.setEnabled(on and n > 0)
        self.btn_pick_auto.setEnabled(on and n < total)
        self.btn_pick_clear.setEnabled(on and n > 0)
        if hasattr(self, "btn_pick_order_win"):
            self.btn_pick_order_win.setEnabled(on)
        self._refresh_pick_site_combo()
        if not on:
            self.lbl_pick_status.setStyleSheet("")
            self.lbl_pick_status.setText(
                "Route applied. Numbers on the map match drive order. "
                "Re-plan with PLAN ROUTE on Setup.")
            if sync_dialog:
                self._hide_route_pick_dialog()
            return
        letters = self._pick_site_letters()
        self.lbl_pick_status.setStyleSheet(
            "font-size:14px;font-weight:700;color:#0d47a1;padding:8px 0;")
        if n >= total:
            self.lbl_pick_status.setText(
                f"All {total} stops set. Tap Apply route.")
        else:
            self.lbl_pick_status.setText(
                f"{self._pick_prompt_text()} — map, dropdown, or Route order window. "
                f"Apply / Auto-finish fills the rest on real streets.")
        if sync_dialog and on and self._route_pick_dialog is not None:
            by_uid = {s["uid"]: s for s in self.state.stops}
            self._route_pick_dialog.sync_from_parent(
                uids=list(self._route_pick_uids),
                stops_by_uid=by_uid,
                letters=letters,
                street_label=self._street_label,
                total=total,
                prompt=self._pick_prompt_text(),
            )

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

    def _route_pick_add(self, uid: str) -> None:
        if not self._route_pick_mode:
            return
        if uid in self._route_pick_uids:
            self.statusBar().showMessage("Already in your route — pick the next site.", 4000)
            return
        self._route_pick_uids.append(uid)
        n = len(self._route_pick_uids)
        total = len(self.state.stops)
        self._refresh_route_pick_ui()
        self._refresh_route_list()
        self._push_state()
        if n >= total:
            self.statusBar().showMessage(
                f"Site {n} added — all sites chosen. Tap Apply route.", 8000)
        else:
            self.statusBar().showMessage(
                f"Site {n} added — {self._pick_prompt_text()}.", 8000)

    def _route_pick_clear(self) -> None:
        if not self._route_pick_mode:
            return
        self._route_pick_uids = []
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
        if not self._route_pick_mode or not self._route_pick_uids:
            self._warn("Choose at least stop 1 from the dropdown, map, or Auto-finish.")
            return
        from core.map_display import apply_manual_order, auto_finish_order

        by_uid = {s["uid"]: s for s in self.state.stops}
        picked = [by_uid[u] for u in self._route_pick_uids if u in by_uid]
        remaining = [s for s in self.state.stops if s["uid"] not in self._route_pick_uids]
        if remaining:
            ordered = auto_finish_order(tuple(self.state.home), picked, remaining, DATA_DIR)
        else:
            ordered = picked
        res = apply_manual_order(tuple(self.state.home), ordered, DATA_DIR)
        self.state.stops = res["order"]
        self.state.route = res["route"]
        self._route_pick_mode = False
        self._route_pick_uids = []
        self._hide_route_pick_dialog()
        self._persist_shift(quiet=True)
        self._refresh_route_list()
        self._refresh_route_pick_ui()
        self._refresh_route_summary_ui()
        self._refresh_field_ready()
        self._push_state(fit=True)
        miles = res["route"].get("miles", 0.0)
        self.statusBar().showMessage(
            f"Route applied: {len(self.state.stops)} stops, {miles:.1f} mi (street-traced sites).",
            10000,
        )
        if hasattr(self, "btn_build"):
            self.btn_build.setEnabled(True)
            self.btn_build.setText("PLAN ROUTE — pick stop order")

    def _highlight_stop_uid(self) -> str | None:
        if self.nav.get("active"):
            rem = self._remaining_drive_stops()
            return rem[0]["uid"] if rem else None
        for s in self.state.stops:
            if not s.get("installed") and not s.get("skipped"):
                return s["uid"]
        return None

    def _optimize_and_route(self, stops):
        self._route_pick_mode = False
        self._route_pick_uids = []
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
                self.btn_build.setText("BUILD OPTIMIZED ROUTE")

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
        if hasattr(self, "lbl_stat_stops"):
            self.lbl_stat_stops.setText(str(len(self.state.stops)))
            self.lbl_stat_miles.setText(f"{miles:.1f}" if self.state.stops else "—")
            self.lbl_stat_kind.setText(kind_short)
        self.lbl_route_stats.setText(
            f"{len(self.state.stops)} stops - {miles:.1f} mi - {kind_long}"
        )
        self._refresh_route_summary_ui()
        self._refresh_workflow_strip()
        self._refresh_field_strip_ui()
        self.btn_start.setText("STOP DRIVING" if self.nav.get("active") else "START DRIVING")
        self.btn_start.setObjectName("stop" if self.nav.get("active") else "go")
        self.btn_start.setStyleSheet("")  # re-evaluate object-name style
        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)

    def _route_item_clicked(self, item):
        self.current_index = self.list_route.row(item)
        self._go_page(2)
        self._center_current()

    # ----------------------------------------------------- Navigation (drive)
    def _toggle_drive(self):
        if self.nav.get("active"):
            self._stop_drive()
        else:
            self._start_drive()

    def _activate_drive(self, remaining: list[dict]):
        """Map follow — highlights next stop number (no blue trace)."""
        start = self._drive_start_point()
        self.nav = {
            "active": True,
            "leg_index": 0,
            "leg_poly": [],
            "stops": remaining,
            "graph": road_router.has_graph(DATA_DIR),
            "off_route_n": 0,
            "_last_reroute": 0.0,
            "phase": "stops",
            "drive_target_uid": remaining[0]["uid"] if remaining else None,
        }
        self._last_leg_push = 0.0
        self._set_nav_leg(start, remaining[0], push_map=True)
        self.bridge.set_follow(True)
        self._update_right(force_map=True)
        self._push_state()
        self._refresh_route_list()
        self._go_page(1)
        g = self.gps.latest()
        if g.get("fix"):
            self._drive_update(g["lat"], g["lon"])

    def _start_drive(self):
        if not self.state.stops:
            self._warn("Build a route first.")
            return
        remaining = [s for s in self.state.stops if not s.get("installed") and not s.get("skipped")]
        if not remaining:
            self._info("All stops are already done.")
            return
        if not road_router.has_graph(DATA_DIR):
            if self.state.offline_mode:
                self._field_notice(
                    "Driving with straight-line legs (no local road map on this laptop).")
            else:
                self._warn(
                    "No offline road map for this area yet.\n\n"
                    "Driving will use straight lines only.\n"
                    "On WiFi: Setup → Download road map → BUILD ROUTE.")
        self._activate_drive(remaining)
        n = len(remaining)
        self.statusBar().showMessage(
            f"Driving — follow map to Site {remaining[0]['id']} ({n} stop(s), then return to start).",
            10000,
        )

    def _stop_drive(self):
        self.nav = {"active": False}
        if hasattr(self, "lbl_drive_banner"):
            self.lbl_drive_banner.hide()
        self.btn_start.setText("START DRIVING")
        self.btn_start.setObjectName("go")
        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)
        self._push_state()
        self.statusBar().showMessage("Driving stopped.", 5000)

    def _maybe_reroute(self, lat: float, lon: float):
        """Offline reroute: one Dijkstra on the saved graph when GPS leaves the leg line."""
        nav = self.nav
        if not nav.get("active") or not nav.get("graph"):
            return
        poly = nav.get("leg_poly") or []
        if len(poly) < 2:
            return
        off_m = road_router.dist_to_polyline_m(lat, lon, poly)
        if off_m > 70:
            nav["off_route_n"] = int(nav.get("off_route_n", 0)) + 1
        else:
            nav["off_route_n"] = 0
        if nav.get("off_route_n", 0) < 3:
            return
        if hasattr(self, "lbl_drive_banner"):
            self.lbl_drive_banner.setText("Off route — recalculating…")
        nav["off_route_n"] = 0
        import time as _time
        if _time.time() - float(nav.get("_last_reroute", 0)) < 12:
            return
        self._reroute_current_leg(lat, lon)

    def _reroute_current_leg(self, lat: float, lon: float):
        import time as _time
        remaining = self._remaining_drive_stops()
        if self.nav.get("phase") == "home":
            home = tuple(self.state.home)
            self._set_nav_leg((lat, lon), {}, push_map=True, to_pt=home)
        elif remaining:
            self._set_nav_leg((lat, lon), remaining[0], push_map=True)
        self.nav["_last_reroute"] = _time.time()
        self._push_state()
        self.statusBar().showMessage("Recalculated — next stop updated on map.", 5000)

    def _drive_update(self, lat: float, lon: float):
        if not self.nav.get("active"):
            return
        self._refresh_drive_leg_trim(lat, lon)
        self._maybe_reroute(lat, lon)
        remaining = self._remaining_drive_stops()
        home = tuple(self.state.home)

        if not remaining:
            d_home = self._dist_m(lat, lon, home[0], home[1])
            if self.nav.get("phase") != "home":
                self.nav["phase"] = "home"
                self.nav["drive_target_uid"] = None
                self._set_nav_leg((lat, lon), {}, push_map=True, to_pt=home)
                self._push_state()
            self.status_route.setText(f"Return to start — {d_home / 1609.34:.1f} mi")
            if d_home < 45:
                self._stop_drive()
                self.statusBar().showMessage("Back at start — driving ended.", 8000)
            return

        self.nav["phase"] = "stops"
        target = remaining[0]
        tlat, tlon = self.state.point(target)
        d = self._dist_m(lat, lon, tlat, tlon)
        gi = self.state.index_of(target["uid"])
        if gi >= 0:
            self.current_index = gi
        if self.nav.get("drive_target_uid") != target["uid"]:
            self.nav["drive_target_uid"] = target["uid"]
            self._set_nav_leg((lat, lon), target, push_map=True)
            self._push_state()
        self._update_drive_banner((lat, lon), (tlat, tlon), target)
        left = len(remaining)
        self.status_route.setText(
            f"Next: Site {target['id']} — {d / 1609.34:.1f} mi"
            f" ({left} left, then home) — {self._street_label(target)}")
        if d < 40 and len(remaining) > 1:
            nxt = remaining[1]
            self.nav["leg_index"] = int(self.nav.get("leg_index", 0)) + 1
            self.nav["drive_target_uid"] = nxt["uid"]
            self._set_nav_leg((lat, lon), nxt, push_map=True)
            self._push_state()

    # ------------------------------------------------------- PicoCount counter
    def _counter_selected_port(self) -> str | None:
        if not hasattr(self, "combo_counter_port"):
            return None
        p = self.combo_counter_port.currentText().strip()
        return p if p and p != "(none)" else None

    def _counter_refresh_ports(self) -> None:
        if not hasattr(self, "combo_counter_port"):
            return
        cur = self.combo_counter_port.currentText()
        self.combo_counter_port.clear()
        ports = picocount.list_serial_ports()
        if not ports:
            self.combo_counter_port.addItem("(none)")
        else:
            for p in ports:
                self.combo_counter_port.addItem(p)
        idx = self.combo_counter_port.findText(cur)
        if idx >= 0:
            self.combo_counter_port.setCurrentIndex(idx)
        elif self.combo_counter_port.count() and self.combo_counter_port.itemText(0) != "(none)":
            pass
        else:
            pr = picocount.probe_port()
            if pr.port:
                i = self.combo_counter_port.findText(pr.port)
                if i >= 0:
                    self.combo_counter_port.setCurrentIndex(i)

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
        if uid:
            self.lbl_counter_unit.setText(f"Next Unit ID on clear: {uid}")
        else:
            self.lbl_counter_unit.setText("")
        if self.state.stops and self.current_index < len(self.state.stops):
            s = self.state.stops[self.current_index]
            parts = []
            if s.get("counter_serial"):
                parts.append(f"Saved counter serial: {s['counter_serial']}")
            if s.get("counter_unit_id"):
                parts.append(f"Unit ID: {s['counter_unit_id']}")
            if s.get("counter_download_path"):
                parts.append("Data downloaded")
            if parts and hasattr(self, "lbl_counter_download"):
                self.lbl_counter_download.setText(" · ".join(parts))

    def _counter_set_busy(self, msg: str) -> None:
        self.lbl_counter_status.setText(msg)
        for w in (
            self.btn_counter_connect,
            self.btn_counter_read_serial,
            self.btn_counter_clear,
            getattr(self, "btn_counter_download", None),
        ):
            if w is not None:
                w.setEnabled(False)

    def _counter_clear_busy(self) -> None:
        for w in (
            self.btn_counter_connect,
            self.btn_counter_read_serial,
            self.btn_counter_clear,
            getattr(self, "btn_counter_download", None),
        ):
            if w is not None:
                w.setEnabled(True)
        self._update_counter_labels()

    def _on_picocount_done(self, res: dict) -> None:
        self._picocount_thread = None
        op = res.pop("_op", "")
        if op == "probe":
            if res.get("ok"):
                self.lbl_counter_status.setText(
                    f"Connection successful — {res.get('message', '')}")
                self.statusBar().showMessage("PicoCount connected.", 6000)
            else:
                self.lbl_counter_status.setText(res.get("message", "Not connected"))
        elif op == "serial":
            if res.get("ok"):
                sn = str(res.get("serial_number", "")).strip()
                if sn and hasattr(self, "txt_serial"):
                    self.txt_serial.setText(sn)
                if self.state.stops and self.current_index < len(self.state.stops):
                    s = self.state.stops[self.current_index]
                    s["counter_serial"] = sn
                    self._persist_shift(quiet=True)
                self.lbl_counter_status.setText(
                    f"Serial {sn or '—'} · {res.get('model', '')} {res.get('firmware', '')}")
                self.statusBar().showMessage("Counter serial read.", 5000)
            else:
                self.lbl_counter_status.setText(res.get("error", "Serial read failed"))
        elif op == "clear_configure":
            if res.get("ok"):
                if self.state.stops and self.current_index < len(self.state.stops):
                    s = self.state.stops[self.current_index]
                    s["counter_unit_id"] = res.get("unit_id", "")
                    s["counter_serial"] = res.get("serial_number", s.get("counter_serial", ""))
                    s["counter_cleared_at"] = ca_now()[1]
                    if res.get("serial_number") and hasattr(self, "txt_serial"):
                        self.txt_serial.setText(str(res["serial_number"]))
                    self._persist_shift(quiet=True)
                self.lbl_counter_status.setText(
                    f"Cleared · Unit ID set to {res.get('unit_id', '')} · serial {res.get('serial_number', '')}")
                self.statusBar().showMessage("Counter cleared and configured for this site.", 8000)
            else:
                self.lbl_counter_status.setText(res.get("error", "Clear/configure failed"))
                self._warn(res.get("error", "Counter operation failed"))
        elif op == "download":
            if res.get("ok"):
                if self.state.stops and self.pickup_index < len(self._installed_stops()):
                    items = self._installed_stops()
                    s = items[min(self.pickup_index, len(items) - 1)]
                    s["counter_download_path"] = res.get("path", "")
                    self._persist_shift(quiet=True)
                    self._refresh_pickup()
                self.lbl_counter_status.setText(
                    f"Downloaded {res.get('bytes', 0):,} bytes → {os.path.basename(res.get('path', ''))}")
                self.statusBar().showMessage("Counter data saved locally.", 8000)
            else:
                self.lbl_counter_status.setText(res.get("error", "Download failed"))
                self._warn(res.get("error", "Could not download counter data"))
        self._counter_clear_busy()
        self._update_counter_labels()

    def _counter_connect(self) -> None:
        self._counter_set_busy("Connecting…")
        res_holder = {"_op": "probe"}
        def wrap(r):
            r["_op"] = "probe"
            self._on_picocount_done(r)
        if self._picocount_thread and self._picocount_thread.isRunning():
            return
        thread = PicocountThread("probe", port=self._counter_selected_port())
        self._picocount_thread = thread
        thread.finished_result.connect(wrap)
        thread.start()

    def _counter_read_serial(self, *, auto: bool = False) -> None:
        if auto and not hasattr(self, "txt_serial"):
            return
        if auto and self.txt_serial.text().strip():
            return
        self._counter_set_busy("Reading counter serial (slow)…")
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
        if QMessageBox.question(
            self,
            "Clear counter",
            f"Clear all data in the counter and set Unit ID to:\n\n  {uid}\n\n"
            "Clock will sync to this PC. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self._counter_set_busy(f"Clearing counter · setting {uid}…")
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
        self._counter_set_busy("Downloading counter data…")
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
            f"Stop {seq} of {total} · Site {s['id']}")
        side = str(s.get("cross_side") or "").strip()
        cross_txt = ""
        if s.get("cross_lat") is not None:
            cross_txt = (
                f"Drive-to point on street line"
                f"{f' (near {side} end)' if side else ''}"
                f" — {float(s['cross_lat']):.5f}, {float(s['cross_lon']):.5f}")
        self.lbl_cross_hint.setText(
            cross_txt or "Crossing not set — BUILD ROUTE after road map download.")
        self.lbl_install_prog.setText(
            f"{s.get('sheet', '')} · {self._street_label(s)} · {done}/{total} installed")
        raw = str(s.get("street", "")).strip()
        self.txt_street.setText(raw if raw and raw.lower() not in ("nan", "none", "nat") else "")
        self.combo_dir.setCurrentText(s.get("direction", "n"))
        self.spin_lanes.setValue(int(s.get("lanes", 2)))
        self.txt_serial.setText(str(s.get("serial", "")))
        self.txt_notes.setPlainText(str(s.get("notes", "")))
        fl, fo = s.get("field_lat"), s.get("field_lon")
        self.lbl_grab.setText(f"Field GPS: {fl:.5f}, {fo:.5f}" if fl else "")
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
        photo = str(s.get("install_photo_path") or "").strip()
        if hasattr(self, "lbl_install_photo"):
            if photo and os.path.isfile(photo):
                self.lbl_install_photo.setText(f"Photo: {os.path.basename(photo)}")
            elif photo:
                self.lbl_install_photo.setText("Photo path missing on disk")
            else:
                self.lbl_install_photo.setText("")
        self._update_compass_labels(self.gps.latest())
        self._update_counter_labels()
        if self.state.stops and self.current_index < len(self.state.stops):
            s = self.state.stops[self.current_index]
            uid = s.get("uid")
            if uid != self._counter_serial_grab_uid and not str(s.get("serial", "")).strip():
                self._counter_serial_grab_uid = uid
                QTimer.singleShot(600, lambda: self._counter_read_serial(auto=True))

    def _on_install_dir_changed(self, *_):
        self._schedule_autosave()
        self._update_counter_labels()

    def _field_photo_dir(self) -> str:
        d = os.path.join(DATA_DIR, "field_photos", self.state.profile)
        os.makedirs(d, exist_ok=True)
        return d

    def _attach_install_photo(self):
        if not self.state.stops or self.current_index >= len(self.state.stops):
            self._warn("Select a stop on Route or Install first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Install photo", "",
            "Images (*.png *.jpg *.jpeg *.webp);;All (*.*)",
        )
        if not path:
            return
        s = self.state.stops[self.current_index]
        ext = os.path.splitext(path)[1] or ".jpg"
        dest = os.path.join(
            self._field_photo_dir(), f"site_{s.get('id', self.current_index)}{ext}")
        try:
            shutil.copy2(path, dest)
        except OSError as exc:
            self._warn(f"Could not save photo:\n{exc}")
            return
        s["install_photo_path"] = dest
        self._persist_shift(quiet=True)
        self._refresh_install()
        self.statusBar().showMessage("Install photo saved locally.", 5000)

    def _clear_install_photo(self):
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return
        s = self.state.stops[self.current_index]
        s.pop("install_photo_path", None)
        self._persist_shift(quiet=True)
        self._refresh_install()

    def _set_dir_from_compass(self):
        g = self.gps.latest()
        hdg = g.get("heading_display") or g.get("heading_locked") or g.get("heading")
        if hdg is None:
            self._warn("No compass reading yet. Drive a short distance, then stop.")
            return
        card = self._heading_cardinal(hdg)
        pick = {"N": "n", "E": "e", "S": "s", "W": "w", "NE": "n", "NW": "n", "SE": "s", "SW": "s"}
        self.combo_dir.setCurrentText(pick.get(card, "n"))
        self.statusBar().showMessage(f"Direction set from compass: {hdg:.0f}° ({card})", 5000)

    def _grab_gps_here(self):
        g = self.gps.latest()
        lat, lon = (g["lat"], g["lon"]) if g.get("fix") else gps_reader.get_fix()
        if lat is None:
            self._warn("No GPS fix. Clear sky view helps.")
            return
        s = self.state.stops[self.current_index]
        s["field_lat"], s["field_lon"] = lat, lon
        sats = g.get("satellites", 0) if g.get("fix") else 0
        self.lbl_grab.setText(f"Field GPS: {lat:.5f}, {lon:.5f}  ({sats} sats)")
        prefer_online = self._internet_allowed()
        street, src = geo.street_for_field(lat, lon, DATA_DIR, prefer_online=prefer_online)
        if street:
            self.txt_street.setText(street)
            hint = "online" if src == "online" else "offline road map"
            self.statusBar().showMessage(f"Install GPS saved — street from {hint}.", 5000)
        else:
            excel_st = str(s.get("street", "")).strip()
            if excel_st and not excel_st.lower().startswith("site "):
                self.txt_street.setText(excel_st)
                self.statusBar().showMessage("Install GPS saved — street from Excel.", 5000)
            else:
                self.statusBar().showMessage(
                    "Install GPS saved. Type street or download road map for offline names.", 6000)
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

    def _commit_install(self, installed: bool):
        if not self.state.stops or self.current_index >= len(self.state.stops):
            return
        s = self.state.stops[self.current_index]
        self._push_undo(
            "install" if installed else "skip",
            s["uid"],
            self._snapshot_stop(s),
            site_id=s["id"],
            current_index=self.current_index,
        )
        notes = self.txt_notes.toPlainText()
        d, lanes, serial = geo.parse_dictation(notes, self.combo_dir.currentText(),
                                               self.spin_lanes.value(), self.txt_serial.text())
        date, exact = ca_now()
        s.update({"street": self.txt_street.text().strip(), "direction": d, "lanes": lanes,
                  "serial": serial, "notes": notes, "installed": installed, "skipped": not installed,
                  "date": date, "exact_time": exact})
        self._flush_install_form()
        self._persist_shift(quiet=True)
        self._push_state()
        self._refresh_route_list()
        self._refresh_audit()
        self._nav_install(1)

    def _nav_install(self, step: int):
        if not self.state.stops:
            return
        self._flush_install_form()
        self._persist_shift(quiet=True)
        self.current_index = max(0, min(len(self.state.stops) - 1, self.current_index + step))
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
            if self.pages.currentIndex() == 2:
                self._flush_install_form()
            self._persist_shift(quiet=True)
            self.gps.stop()
        except Exception:
            pass
        super().closeEvent(event)


def main():
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)
    app = QApplication(sys.argv)
    app.setApplicationName("Traffic Deployer")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
