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

from PySide6.QtCore import Qt, QTimer, QUrl, QThread
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
    QDoubleSpinBox, QProgressDialog, QScrollArea, QSizePolicy,
)

import gps_reader
import local_server
import road_router
import voice_nav
from voice_nav import DriveVoiceAnnouncer, NavVoice
from bridge import MapBridge
from core import export, geo, ingest, validate
from core.field_ready import TOMORROW_STEPS, check_all
from core.offline_gate import evaluate as offline_gate_eval
from core.state import RouteState, ca_now
from ui.paths import (
    APP_DIR, DATA_DIR, DEMO_CSV, DEMO_DIR, DEMO_EST, DIRECTIONS, UNDO_FIELDS, VENDOR_DIR, WEB_DIR,
)
from ui.threads import DownloadRoadsThread, RouteOptimizeThread, SmokeTestThread
from ui.web_page import AppWebPage, ensure_qwebchannel_js
from ui_themes import normalize_theme, qt_stylesheet
from version import APP_NAME, APP_VERSION, APP_TAGLINE


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1320, 860)
        self.state = RouteState(DATA_DIR, profile="DEFAULT")
        self.state.load()
        self.state.theme = normalize_theme(self.state.theme)
        if str(getattr(self.state, "voice_style", "female")).lower() == "vader":
            self.state.voice_style = "female"
            self.state.save()
        self.setStyleSheet(qt_stylesheet(self.state.theme))
        if self.state.default_home:
            self.state.apply_default_home()
        self.current_index = min(self.state.current_index, max(0, len(self.state.stops) - 1))
        self.pickup_index = self.state.pickup_index
        self.trail: list[list[float]] = []
        self.excel_paths = [p for p in self.state.excel_paths if os.path.isfile(p)]
        self.est_paths = [p for p in self.state.est_paths if os.path.isfile(p)]
        self.state.excel_paths = list(self.excel_paths)
        self.state.est_paths = list(self.est_paths)
        self._map_preview_stops: list[dict] = []
        self.nav: dict = {"active": False}
        self._nav_thread = None
        self.voice = NavVoice()
        self.voice.enabled = bool(getattr(self.state, "voice_nav", True))
        self.voice_announcer = DriveVoiceAnnouncer(self.voice)
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
        QTimer.singleShot(1200, self._refresh_voice_hint)
        QTimer.singleShot(2500, self._maybe_field_startup_dialog)

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
        side.setFixedWidth(370)
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._wrap_scroll(self._page_setup()))  # 0
        self.pages.addWidget(self._page_route())                     # 1
        self.pages.addWidget(self._wrap_scroll(self._page_install())) # 2
        self.pages.addWidget(self._page_pickup())                    # 3
        self.pages.addWidget(self._page_audit())                     # 4
        side_lay.addWidget(self.pages)
        body.addWidget(side)

        # Right side: placeholder until a route exists, then the map.
        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(self._placeholder())  # 0
        self.right_stack.addWidget(self.view)            # 1
        body.addWidget(self.right_stack, 1)

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
        self._update_right()

    def _wrap_scroll(self, w: QWidget) -> QWidget:
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(w)
        return sc

    def _placeholder(self) -> QWidget:
        w = QWidget()
        w.setObjectName("placeholder")
        v = QVBoxLayout(w)
        v.addStretch(1)
        t = QLabel("Traffic Deployer")
        t.setObjectName("phTitle")
        t.setAlignment(Qt.AlignCenter)
        msg = QLabel("Set your start point and upload your files on the left,\nthen press BUILD OPTIMIZED ROUTE.\n\nThe map of your work area will appear here.")
        msg.setObjectName("phText")
        msg.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        v.addSpacing(10)
        v.addWidget(msg)
        v.addStretch(1)
        return w

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 8, 14, 8)
        brand = QLabel(f"{APP_NAME}  v{APP_VERSION}")
        brand.setObjectName("brand")
        lay.addWidget(brand)
        b_about = QPushButton("About")
        b_about.setObjectName("aboutBtn")
        b_about.clicked.connect(self._show_about)
        lay.addWidget(b_about)
        lay.addStretch(1)
        for idx, name in enumerate(("Setup", "Route", "Install", "Pickup", "Audit")):
            b = QPushButton(name)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, i=idx: self._go_page(i))
            lay.addWidget(b)
            if idx == 0:
                b.setChecked(True)
            setattr(self, f"_modebtn_{idx}", b)
        lay.addStretch(1)
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
            getattr(self, f"_modebtn_{j}").setChecked(j == i)
        if i == 1:
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

    # ---------------------------------------------------------- Setup page
    def _page_setup(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)

        v.addWidget(self._h("PROFILE"))
        self.txt_profile = QLineEdit(self.state.profile)
        self.txt_profile.setPlaceholderText("e.g. DEFAULT, WEEK9")
        row_prof = QHBoxLayout()
        b_prof = QPushButton("Load / switch")
        b_prof.clicked.connect(self._switch_profile)
        b_save_as = QPushButton("Save as new profile")
        b_save_as.clicked.connect(self._save_profile_as)
        row_prof.addWidget(b_prof)
        row_prof.addWidget(b_save_as)
        v.addWidget(self.txt_profile)
        v.addLayout(row_prof)
        b_save_now = QPushButton("Save progress now")
        b_save_now.clicked.connect(self._save_shift_now)
        v.addWidget(b_save_now)
        self.lbl_save_hint = QLabel(
            "Work auto-saves every ~45s and when you close. Re-build route keeps installs.")
        self.lbl_save_hint.setWordWrap(True)
        self.lbl_save_hint.setStyleSheet("color:#6b7280;font-size:12px;")
        v.addWidget(self.lbl_save_hint)

        v.addWidget(self._h("FIELD READINESS"))
        self.lbl_field_score = QLabel("")
        self.lbl_field_score.setStyleSheet("font-weight:800;font-size:15px;")
        v.addWidget(self.lbl_field_score)
        self.lbl_field_checks = QLabel("")
        self.lbl_field_checks.setWordWrap(True)
        self.lbl_field_checks.setStyleSheet("font-size:12px;line-height:1.35;")
        v.addWidget(self.lbl_field_checks)
        self.lbl_field_tomorrow = QLabel("\n".join(f"• {s}" for s in TOMORROW_STEPS))
        self.lbl_field_tomorrow.setWordWrap(True)
        self.lbl_field_tomorrow.setStyleSheet("color:#475569;font-size:12px;")
        v.addWidget(self.lbl_field_tomorrow)
        row_ready = QHBoxLayout()
        b_refresh_ready = QPushButton("Refresh check")
        b_refresh_ready.clicked.connect(self._refresh_field_ready)
        b_smoke = QPushButton("Run smoke test")
        b_smoke.clicked.connect(self._run_smoke_test)
        row_ready.addWidget(b_refresh_ready)
        row_ready.addWidget(b_smoke)
        v.addLayout(row_ready)

        v.addWidget(self._h("STARTING POINT"))
        self.lbl_origin = QLabel("")
        v.addWidget(self.lbl_origin)
        b_usb = QPushButton("Read USB GPS -> set origin")
        b_usb.clicked.connect(self._origin_from_gps)
        v.addWidget(b_usb)
        self.txt_address = QLineEdit()
        self.txt_address.setPlaceholderText("123 Main St, Garden Grove, CA")
        b_addr = QPushButton("Search address (online)")
        b_addr.clicked.connect(self._origin_from_address)
        self.btn_address = b_addr
        v.addWidget(self.txt_address)
        v.addWidget(b_addr)
        row = QHBoxLayout()
        self.spin_lat = QDoubleSpinBox(); self.spin_lat.setDecimals(5)
        self.spin_lat.setRange(-90, 90); self.spin_lat.setValue(self.state.home[0])
        self.spin_lon = QDoubleSpinBox(); self.spin_lon.setDecimals(5)
        self.spin_lon.setRange(-180, 180); self.spin_lon.setValue(self.state.home[1])
        row.addWidget(self.spin_lat); row.addWidget(self.spin_lon)
        v.addLayout(row)
        b_coords = QPushButton("Save manual coordinates")
        b_coords.clicked.connect(self._origin_from_coords)
        v.addWidget(b_coords)
        b_default = QPushButton("Save as DEFAULT start (GPS coords)")
        b_default.setObjectName("primary")
        b_default.clicked.connect(self._save_default_home)
        v.addWidget(b_default)
        b_load_def = QPushButton("Load saved default start")
        b_load_def.clicked.connect(self._load_default_home)
        v.addWidget(b_load_def)

        v.addWidget(self._h("GO OFFLINE"))
        self.lbl_offline = QLabel("")
        self.lbl_offline.setWordWrap(True)
        v.addWidget(self.lbl_offline)
        self.btn_offline = QPushButton("READY FOR OFFLINE")
        self.btn_offline.setObjectName("go")
        self.btn_offline.clicked.connect(self._ready_offline)
        v.addWidget(self.btn_offline)

        v.addWidget(self._h("GPS RECEIVER"))
        self.combo_port = QComboBox()
        v.addWidget(self.combo_port)
        rowg = QHBoxLayout()
        b_refresh_ports = QPushButton("Refresh ports")
        b_refresh_ports.clicked.connect(self._refresh_ports)
        b_useport = QPushButton("Use selected port")
        b_useport.clicked.connect(self._set_gps_port)
        rowg.addWidget(b_refresh_ports)
        rowg.addWidget(b_useport)
        v.addLayout(rowg)
        self._refresh_ports()

        v.addWidget(self._h("FIELD FILES"))
        b_excel = QPushButton("Add Excel/CSV file(s)")
        b_excel.clicked.connect(self._pick_excel)
        v.addWidget(b_excel)
        self.list_excel = QListWidget(); self.list_excel.setMaximumHeight(70)
        v.addWidget(self.list_excel)
        b_est = QPushButton("Add .EST map file(s)")
        b_est.clicked.connect(self._pick_est)
        v.addWidget(b_est)
        v.addWidget(QLabel("Map files (Day# from upload name):"))
        self.list_est = QListWidget(); self.list_est.setMaximumHeight(90)
        v.addWidget(self.list_est)
        b_clear = QPushButton("Clear file lists")
        b_clear.clicked.connect(self._clear_files)
        v.addWidget(b_clear)
        b_demo = QPushButton("Load demo files (desk test)")
        b_demo.clicked.connect(self._load_demo_files)
        v.addWidget(b_demo)

        v.addWidget(self._h("BUILD"))
        b_roads = QPushButton("Download road map for these sites (online)")
        b_roads.clicked.connect(self._download_roads)
        self.btn_download_roads = b_roads
        v.addWidget(b_roads)
        b_import_roads = QPushButton("Import road map from file (.graphml)")
        b_import_roads.clicked.connect(self._import_roads)
        self.btn_import_roads = b_import_roads
        v.addWidget(b_import_roads)
        self.lbl_roads_hint = QLabel(
            "Work Wi‑Fi often blocks download — copy road_graph.graphml from home, then Import.")
        self.lbl_roads_hint.setWordWrap(True)
        self.lbl_roads_hint.setStyleSheet("color:#6b7280;font-size:12px;")
        v.addWidget(self.lbl_roads_hint)
        b_sync = QPushButton("BUILD OPTIMIZED ROUTE")
        b_sync.setObjectName("primary")
        b_sync.clicked.connect(self._build_route_from_uploads)
        v.addWidget(b_sync)
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

    def _maybe_field_startup_dialog(self):
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
        v.setContentsMargins(16, 14, 16, 14)
        v.addWidget(self._h("ROUTE"))
        self.lbl_route_stats = QLabel("No route yet.")
        v.addWidget(self.lbl_route_stats)
        self.lbl_drive_banner = QLabel("")
        self.lbl_drive_banner.setWordWrap(True)
        self.lbl_drive_banner.setStyleSheet(
            "background:#e3f2fd;border:1px solid #90caf9;border-radius:6px;"
            "padding:8px;font-weight:700;font-size:13px;color:#0d47a1;")
        self.lbl_drive_banner.hide()
        v.addWidget(self.lbl_drive_banner)
        self.chk_voice = QCheckBox("Voice guidance (offline)")
        self.chk_voice.setChecked(bool(self.state.voice_nav))
        self.chk_voice.stateChanged.connect(self._on_voice_toggle)
        v.addWidget(self.chk_voice)
        row_voice = QHBoxLayout()
        b_voice_test = QPushButton("Test voice")
        b_voice_test.clicked.connect(self._test_voice)
        row_voice.addWidget(b_voice_test)
        self.lbl_voice_hint = QLabel("")
        self.lbl_voice_hint.setStyleSheet("color:#6b7280;font-size:11px;")
        row_voice.addWidget(self.lbl_voice_hint, 1)
        v.addLayout(row_voice)
        self._refresh_voice_hint()
        self.chk_show_guide = QCheckBox("Show guiding route (blue)")
        self.chk_show_guide.setChecked(True)
        self.chk_show_guide.stateChanged.connect(lambda: self._push_state())
        v.addWidget(self.chk_show_guide)
        self.chk_show_segments = QCheckBox("Show site lines (purple)")
        self.chk_show_segments.setChecked(True)
        self.chk_show_segments.stateChanged.connect(lambda: self._push_state())
        v.addWidget(self.chk_show_segments)
        row_day = QHBoxLayout()
        row_day.addWidget(QLabel("Map on screen:"))
        self.combo_day = QComboBox()
        self.combo_day.currentTextChanged.connect(self._on_day_filter_changed)
        row_day.addWidget(self.combo_day, 1)
        v.addLayout(row_day)
        self.btn_start = QPushButton("START DRIVING")
        self.btn_start.setObjectName("go")
        self.btn_start.clicked.connect(self._toggle_drive)
        v.addWidget(self.btn_start)
        lbl_drive = QLabel(
            "While driving: map follow + blue leg. Banner shows next turn; voice optional below.")
        lbl_drive.setWordWrap(True)
        lbl_drive.setStyleSheet("color:#475569;font-size:12px;")
        v.addWidget(lbl_drive)
        b_fit = QPushButton("Zoom to all stops")
        b_fit.clicked.connect(lambda: self._push_state(fit=True))
        v.addWidget(b_fit)
        self.list_route = QListWidget()
        self.list_route.itemClicked.connect(self._route_item_clicked)
        v.addWidget(self.list_route, 1)
        b_reopt = QPushButton("Re-optimize order")
        b_reopt.clicked.connect(self._reoptimize)
        v.addWidget(b_reopt)
        b_reset = QPushButton("Clear shift data...")
        b_reset.clicked.connect(self._reset_route)
        v.addWidget(b_reset)
        return w

    # -------------------------------------------------------- Install page
    def _page_install(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        self.lbl_install_title = QLabel("No stop selected.")
        self.lbl_install_title.setProperty("role", "title")
        v.addWidget(self.lbl_install_title)
        self.lbl_install_prog = QLabel("")
        v.addWidget(self.lbl_install_prog)
        self.lbl_street_warn = QLabel("")
        self.lbl_street_warn.setStyleSheet("color:#c62828;font-weight:700;")
        self.lbl_street_warn.setWordWrap(True)
        v.addWidget(self.lbl_street_warn)
        self.lbl_compass = QLabel("Compass: waiting for GPS...")
        self.lbl_compass.setStyleSheet("font-weight:700;font-size:14px;")
        v.addWidget(self.lbl_compass)
        self.lbl_compass_sub = QLabel("")
        self.lbl_compass_sub.setStyleSheet("color:#6b7280;font-size:12px;")
        v.addWidget(self.lbl_compass_sub)
        b_comp_dir = QPushButton("Set direction from compass")
        b_comp_dir.clicked.connect(self._set_dir_from_compass)
        v.addWidget(b_comp_dir)
        v.addWidget(QLabel("Street name:"))
        self.txt_street = QLineEdit()
        self.txt_street.textChanged.connect(self._schedule_autosave)
        v.addWidget(self.txt_street)
        row = QHBoxLayout()
        self.combo_dir = QComboBox(); self.combo_dir.addItems(DIRECTIONS)
        self.combo_dir.currentTextChanged.connect(lambda *_: self._schedule_autosave())
        self.spin_lanes = QSpinBox(); self.spin_lanes.setRange(1, 20); self.spin_lanes.setValue(2)
        self.spin_lanes.valueChanged.connect(lambda *_: self._schedule_autosave())
        self.txt_serial = QLineEdit(); self.txt_serial.setPlaceholderText("Serial #")
        self.txt_serial.textChanged.connect(self._schedule_autosave)
        row.addWidget(QLabel("Dir")); row.addWidget(self.combo_dir)
        row.addWidget(QLabel("Lanes")); row.addWidget(self.spin_lanes)
        v.addLayout(row)
        v.addWidget(self.txt_serial)
        v.addWidget(QLabel("Field notes / dictation:"))
        self.txt_notes = QPlainTextEdit(); self.txt_notes.setMaximumHeight(80)
        self.txt_notes.textChanged.connect(self._schedule_autosave)
        v.addWidget(self.txt_notes)
        b_grab = QPushButton("Grab GPS Here (precise)")
        b_grab.clicked.connect(self._grab_gps_here)
        v.addWidget(b_grab)
        self.lbl_grab = QLabel("")
        v.addWidget(self.lbl_grab)
        row2 = QHBoxLayout()
        b_install = QPushButton("INSTALL  (I)")
        b_install.setObjectName("fieldPrimary")
        b_install.clicked.connect(lambda: self._commit_install(True))
        b_skip = QPushButton("SKIP  (S)")
        b_skip.setObjectName("fieldSkip")
        b_skip.clicked.connect(lambda: self._commit_install(False))
        row2.addWidget(b_install)
        row2.addWidget(b_skip)
        v.addLayout(row2)
        self.btn_undo_install = QPushButton("Undo last action  (Ctrl+Z)")
        self.btn_undo_install.setEnabled(False)
        self.btn_undo_install.clicked.connect(self._undo_last_action)
        v.addWidget(self.btn_undo_install)
        lbl_keys = QLabel("Shortcuts: I install · S skip · G grab GPS · N/P prev/next")
        lbl_keys.setWordWrap(True)
        lbl_keys.setStyleSheet("color:#6b7280;font-size:11px;")
        v.addWidget(lbl_keys)
        b_show = QPushButton("Show on map")
        b_show.clicked.connect(self._center_current)
        v.addWidget(b_show)
        v.addStretch(1)
        row3 = QHBoxLayout()
        b_prev = QPushButton("< Prev"); b_prev.clicked.connect(lambda: self._nav_install(-1))
        b_next = QPushButton("Next >"); b_next.clicked.connect(lambda: self._nav_install(1))
        row3.addWidget(b_prev); row3.addWidget(b_next)
        v.addLayout(row3)
        return w

    # --------------------------------------------------------- Pickup page
    def _page_pickup(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 14, 16, 14)
        v.addWidget(self._h("PICK-UP"))
        self.lbl_pickup_prog = QLabel("")
        v.addWidget(self.lbl_pickup_prog)
        self.chk_pickup_pending = QCheckBox("Show only not picked up yet")
        self.chk_pickup_pending.setChecked(True)
        self.chk_pickup_pending.stateChanged.connect(self._refresh_pickup)
        v.addWidget(self.chk_pickup_pending)
        self.list_pickup = QListWidget()
        self.list_pickup.itemClicked.connect(self._pickup_item_clicked)
        v.addWidget(self.list_pickup, 1)
        self.lbl_pickup_cur = QLabel("")
        v.addWidget(self.lbl_pickup_cur)
        b_sec = QPushButton("SECURED (picked up)")
        b_sec.setObjectName("primary")
        b_sec.clicked.connect(self._mark_pickup)
        v.addWidget(b_sec)
        self.btn_undo_pickup = QPushButton("Undo last action  (Ctrl+Z)")
        self.btn_undo_pickup.setEnabled(False)
        self.btn_undo_pickup.clicked.connect(self._undo_last_action)
        v.addWidget(self.btn_undo_pickup)
        row_pick = QHBoxLayout()
        b_pick_prev = QPushButton("< Prev")
        b_pick_prev.clicked.connect(lambda: self._nav_pickup(-1))
        b_pick_next = QPushButton("Next >")
        b_pick_next.clicked.connect(lambda: self._nav_pickup(1))
        row_pick.addWidget(b_pick_prev)
        row_pick.addWidget(b_pick_next)
        v.addLayout(row_pick)
        return w

    # ---------------------------------------------------------- Audit page
    def _page_audit(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 14, 16, 14)
        v.addWidget(self._h("END OF DAY AUDIT"))
        self.lbl_audit = QLabel("")
        self.lbl_audit.setWordWrap(True)
        v.addWidget(self.lbl_audit)
        b_xlsx = QPushButton("Export Excel (.xlsx)")
        b_xlsx.setObjectName("primary")
        b_xlsx.clicked.connect(self._export_excel)
        v.addWidget(b_xlsx)
        b_xlsx_quick = QPushButton("Quick export Excel → default folder")
        b_xlsx_quick.clicked.connect(self._export_excel_quick)
        v.addWidget(b_xlsx_quick)
        self.lbl_export_hint = QLabel("")
        self.lbl_export_hint.setWordWrap(True)
        self.lbl_export_hint.setStyleSheet("color:#6b7280;font-size:12px;")
        v.addWidget(self.lbl_export_hint)
        self._refresh_export_hint()
        b_csv = QPushButton("Export CSV")
        b_csv.clicked.connect(self._export_csv)
        v.addWidget(b_csv)
        b_csv_quick = QPushButton("Quick export CSV → default folder")
        b_csv_quick.clicked.connect(self._export_csv_quick)
        v.addWidget(b_csv_quick)
        v.addStretch(1)
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
            g = self.gps.latest()
            if g.get("fix") and g.get("lat") is not None:
                leg = self._trim_poly_ahead(leg, g["lat"], g["lon"])
            self.bridge.send_drive_leg(leg, active=True)

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

    def _advance_nav_voice(self, lat: float, lon: float, target: dict | None = None):
        maneuvers = self.nav.get("maneuvers") or []
        if not maneuvers or not self.state.voice_nav:
            return
        step = int(self.nav.get("step", 0))
        if step >= len(maneuvers):
            return
        m = maneuvers[step]
        dist_ft = self._dist_m(lat, lon, m["lat"], m["lon"]) * 3.28084
        site_id = str(target.get("id", "")) if target else None
        self.voice_announcer.on_step(
            step, m.get("type", "straight"), m.get("street", ""), dist_ft, site_id=site_id)
        if dist_ft < 80 and step < len(maneuvers) - 1:
            self.nav["step"] = step + 1

    def _on_voice_toggle(self):
        on = self.chk_voice.isChecked()
        self.state.voice_nav = on
        self.voice.enabled = on
        self.state.save()
        if not on:
            self.voice.flush()

    def _test_voice(self):
        if not voice_nav.tts_available():
            self._warn(f"Voice not available:\n\n{voice_nav.tts_error() or 'pyttsx3 missing'}")
            return
        self.voice.test()
        self._refresh_voice_hint()

    def _refresh_voice_hint(self):
        if not hasattr(self, "lbl_voice_hint"):
            return
        if not voice_nav.tts_available():
            self.lbl_voice_hint.setText("Voice unavailable — install pyttsx3")
        elif self.voice.ready:
            self.lbl_voice_hint.setText(f"Voice: {self.voice.voice_name}")
        else:
            self.lbl_voice_hint.setText("Voice starting…")

    def _refresh_drive_leg_trim(self, lat: float, lon: float):
        import time as _time
        now = _time.time()
        if now - self._last_leg_push < 1.5:
            return
        self._last_leg_push = now
        base = self.nav.get("leg_poly") or []
        if len(base) < 2:
            return
        self.bridge.send_drive_leg(self._trim_poly_ahead(base, lat, lon), active=True)

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
            return base
        day = self.combo_day.currentText()
        if day == "All maps":
            return base
        return [s for s in base if s.get("sheet") == day]

    def _refresh_map_preview(self):
        """Show every site begin/end line as soon as Excel + .EST are loaded (before BUILD ROUTE)."""
        if self.state.stops:
            self._map_preview_stops = []
            return
        if not self.excel_paths or not self.est_paths:
            self._map_preview_stops = []
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
        except Exception:
            self._map_preview_stops = []
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

    def _push_state(self, fit: bool = False):
        driving = bool(self.nav.get("active"))
        preview = bool(self._map_preview_stops) and not self.state.stops
        st = {
            "theme": self.state.theme,
            "home": list(self.state.home),
            "stops": self._stops_for_map(),
            "route": self._display_route(),
            "fit": fit,
            "driving": driving,
            "map_mode": "drive" if driving else ("preview" if preview else "plan"),
            "drive_target_uid": self.nav.get("drive_target_uid") if driving else None,
            "show_guide": False if driving else self.chk_show_guide.isChecked(),
            "show_segments": self.chk_show_segments.isChecked(),
            "show_crossings": self.chk_show_segments.isChecked() and not driving,
            "show_badges": True,
        }
        self.bridge.send_state(st)
        if driving and self.nav.get("leg_poly"):
            self.bridge.send_drive_leg(self.nav["leg_poly"], active=True)
        miles = self.state.route.get("miles", 0.0)
        drive = (miles / 30.0) * 60 if miles else 0
        self.status_route.setText(f"Stops: {len(self.state.stops)}   Route: {miles:.1f} mi   ~{drive:.0f} min")

    def _on_stop_clicked(self, uid: str):
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
            if not self.trail or self._moved(self.trail[-1], (lat, lon)):
                self.trail.append([lat, lon])
                if len(self.trail) > 2000:
                    self.trail = self.trail[-2000:]
            hdg = g.get("heading_display") or g.get("heading_locked") or g.get("heading")
            self.bridge.send_gps({
                "lat": lat, "lon": lon, "heading": hdg, "trail": self.trail,
                "heading_mode": g.get("heading_mode"), "speed_mps": g.get("speed_mps"),
            })
            self._update_compass_labels(g)
            self.status_gps.setText(f"GPS: FIX  {g.get('satellites', 0)} sats   {lat:.5f}, {lon:.5f}")
            if self.nav.get("active"):
                self._drive_update(lat, lon)
            if hasattr(self, "lbl_field_score") and not hasattr(self, "_gps_ready_refreshed"):
                self._gps_ready_refreshed = True
                self._refresh_field_ready()
        elif g.get("connected"):
            self.status_gps.setText(f"GPS: searching... {g.get('satellites', 0)} sats (need clear sky)")
        else:
            self.status_gps.setText("GPS: not detected (check USB receiver)")

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
        self.state.save()
        self._push_state(fit=True)
        self.statusBar().showMessage("Loaded saved default start.", 4000)

    def _ready_offline(self):
        if self.state.offline_mode:
            self._info("Already in offline mode. All field data saves locally.")
            return
        r = check_all(APP_DIR, probe_gps=False, stop_server_after=False)
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
        self._refresh_offline_ui()
        self.statusBar().showMessage("OFFLINE MODE — field ready. No online calls on the road.", 10000)
        self._info(
            "Ready for offline.\n\n"
            "• Route and road map stored locally\n"
            "• GPS, installs, and exports work offline\n"
            "• No address lookup or map downloads on the road"
        )

    def _refresh_offline_ui(self):
        on = self.state.offline_mode
        self.btn_offline.setText("OFFLINE — FIELD READY" if on else "READY FOR OFFLINE")
        self.btn_offline.setEnabled(not on)
        if on:
            self.lbl_offline.setText("Offline mode ON. Everything saves locally. No internet used.")
            self.lbl_offline.setStyleSheet("color:#138a3e;font-weight:700;")
        else:
            self.lbl_offline.setText("While online: download road map + build route, then tap Ready for Offline.")
            self.lbl_offline.setStyleSheet("color:#6b7280;")
        self.txt_address.setEnabled(not on)
        if hasattr(self, "btn_address"):
            self.btn_address.setEnabled(not on)
        if hasattr(self, "btn_download_roads"):
            self.btn_download_roads.setEnabled(not on)
        if hasattr(self, "btn_import_roads"):
            self.btn_import_roads.setEnabled(not on)

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
        if self.state.offline_mode:
            self._warn("Offline mode — use GPS coordinates for your start point.")
            return
        addr = self.txt_address.text().strip()
        if not addr:
            return
        lat, lon = geo.geocode_address(addr)
        if lat is not None:
            self._set_origin(lat, lon, "Origin set from address.")
        else:
            self._warn("Address not found (need internet, or try coordinates).")

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
        if self.state.offline_mode:
            self._warn("Offline mode — road map is already stored locally.")
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

        report = validate.validate_build(self.excel_paths, cfgs, sites, stops)
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
        self.statusBar().showMessage(f"Loaded {len(stops)} sites - optimizing best route...", 5000)
        self._optimize_and_route(merged)

    @staticmethod
    def _street_label(s: dict) -> str:
        st = str(s.get("street", "")).strip()
        if not st or st.lower() in ("nan", "none", "nat"):
            return f"Site {s.get('id', '')}"
        return st

    def _optimize_and_route(self, stops):
        if not road_router.has_graph(DATA_DIR):
            self._warn(
                "Download the road map first (Setup tab → Download road map).\n\n"
                "That is required for accurate routes that follow real streets and "
                "cross each site line efficiently.")
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
        thread = RouteOptimizeThread(list(stops), tuple(self.state.home), DATA_DIR)
        self._route_thread = thread

        def on_progress(msg: str):
            dlg.setLabelText(f"{msg}\n\nElapsed: {int(_time.time() - t0)}s")

        def tick():
            pass  # progress_text from worker updates the label

        def done(res):
            etimer.stop()
            dlg.close()
            self._route_thread = None
            if not res.get("ok"):
                self._warn(f"Routing failed: {res.get('error', 'unknown')}")
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
            kind = "real roads / segment lines" if res["route"].get("graph") else "straight-line"
            self.statusBar().showMessage(
                f"Route ready: {len(res['order'])} stops, {miles:.1f} mi - {kind}", 9000)
            self._refresh_field_ready()

        def canceled():
            etimer.stop()
            self._stop_worker(thread)
            dlg.close()
            self._route_thread = None

        etimer.timeout.connect(tick)
        dlg.canceled.connect(canceled)
        thread.progress_text.connect(on_progress)
        thread.finished_result.connect(done)
        thread.finished.connect(lambda: etimer.stop())
        thread.start()
        dlg.show()
        tick()

    def _reoptimize(self):
        if self.state.stops:
            self._optimize_and_route(list(self.state.stops))

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
        self._undo_stack.clear()
        self._refresh_undo_ui()
        self.state.clear_shift(wipe_upload_paths=False)
        self.current_index = self.pickup_index = 0
        self._update_right()
        self._push_state(fit=True)
        self._refresh_route_list()
        self.statusBar().showMessage("Shift cleared. Upload files are still listed on Setup.", 8000)

    # --------------------------------------------------------- Route list UI
    def _refresh_route_list(self):
        self.list_route.clear()
        for i, s in enumerate(self.state.stops):
            mark = "OK" if s.get("installed") else "SKIP" if s.get("skipped") else "--"
            self.list_route.addItem(f"[{mark}] {i + 1}. Site {s['id']} - {self._street_label(s)}")
        miles = self.state.route.get("miles", 0.0)
        kind = "segment-line / real roads" if self.state.route.get("graph") else "segment-line (download road map for real streets)"
        self.lbl_route_stats.setText(f"{len(self.state.stops)} stops - {miles:.1f} mi - {kind}")
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
        """Map follow + blue leg to next stop (no turn-by-turn banner or voice)."""
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
        self.voice_announcer.reset()
        if self.state.voice_nav and remaining:
            self.voice_announcer.navigation_started(
                str(remaining[0].get("id", "")),
                self._street_label(remaining[0]),
            )
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
        self.voice.flush()
        self.voice_announcer.reset()
        self.bridge.send_drive_leg([], active=False)
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
        if self.state.voice_nav:
            self.voice_announcer.reroute()
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
        self.bridge.send_drive_leg(self.nav.get("leg_poly") or [], active=True)
        self.statusBar().showMessage("Recalculated leg from your position.", 5000)

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
        self._advance_nav_voice(lat, lon, target)
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

    # ------------------------------------------------------- Install UI/flow
    def _refresh_install(self):
        done, total = self.state.progress_install()
        self.lbl_install_prog.setText(f"Install progress: {done}/{total}")
        if not self.state.stops or self.current_index >= len(self.state.stops):
            self.lbl_install_title.setText("No stop selected.")
            return
        s = self.state.stops[self.current_index]
        self.lbl_install_title.setText(
            f"#{self.current_index + 1}: Site {s['id']}  [{s.get('sheet', '')}] — {self._street_label(s)}")
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
        self._update_compass_labels(self.gps.latest())

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
        prefer_online = not self.state.offline_mode
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
        rep = export.audit(self.state.stops)
        if not self.state.stops:
            self.lbl_audit.setText("No data yet.")
        elif rep["missing"]:
            self.lbl_audit.setText("ACTION NEEDED:\n- " + "\n- ".join(rep["missing"]))
        else:
            self.lbl_audit.setText(f"All {rep['count']} completed sites have full data. Ready to export.")
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
            self.voice.shutdown()
        except Exception:
            pass
        super().closeEvent(event)


def main():
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("Traffic Deployer")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
