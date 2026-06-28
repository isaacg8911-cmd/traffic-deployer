"""Setup tab — files, home, road map, build."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.simple_mode import BUILD_LABEL, COMPACT_UI, SIMPLE_MODE
from ui.widgets import WorkflowStrip, section_group
from ui.counter_ui import apply_volt_check, battery_cell_text


def build_setup_page(win) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    pad = 8 if COMPACT_UI else 14
    v.setContentsMargins(pad, pad, pad, pad)
    v.setSpacing(6 if COMPACT_UI else 10)

    if not SIMPLE_MODE:
        win.workflow_strip = WorkflowStrip()
        v.addWidget(win.workflow_strip)
    else:
        win.workflow_strip = None

    sec_profile = section_group("Profile", v)
    row_prof = QHBoxLayout()
    win.txt_profile = QLineEdit(win.state.profile)
    win.txt_profile.setPlaceholderText("DEFAULT, WEEK9…")
    win.txt_profile.returnPressed.connect(lambda: win._switch_profile())
    row_prof.addWidget(win.txt_profile, 1)
    b_prof = QPushButton("Load")
    b_prof.setObjectName("secondary")
    b_prof.clicked.connect(lambda: win._switch_profile())
    row_prof.addWidget(b_prof, 0)
    b_save_as = QPushButton("Save as…")
    b_save_as.setObjectName("secondary")
    b_save_as.setToolTip("Save current shift under a new profile name")
    b_save_as.clicked.connect(win._save_profile_as)
    row_prof.addWidget(b_save_as, 0)
    sec_profile.addLayout(row_prof)
    b_save_now = QPushButton("Save progress")
    b_save_now.setObjectName("secondary")
    b_save_now.clicked.connect(win._save_shift_now)
    sec_profile.addWidget(b_save_now)
    row_data = QHBoxLayout()
    b_clear_shift = QPushButton("Clear shift data…")
    b_clear_shift.setObjectName("secondary")
    b_clear_shift.setToolTip(
        "Remove sites, route, and install/pickup progress for this profile. "
        "Excel/.EST file lists stay unless you clear them below.")
    b_clear_shift.clicked.connect(win._reset_route)
    row_data.addWidget(b_clear_shift)
    b_start_fresh = QPushButton("Start fresh…")
    b_start_fresh.setObjectName("secondary")
    b_start_fresh.setToolTip("Clear shift data and Excel/.EST file lists — empty map on next launch.")
    b_start_fresh.clicked.connect(win._start_fresh_profile)
    row_data.addWidget(b_start_fresh)
    sec_profile.addLayout(row_data)
    win.lbl_profile_hint = QLabel(
        "Sites on the map at launch = saved shift for this profile (e.g. DEFAULT). "
        "Use Clear shift data to wipe pins and route.")
    win.lbl_profile_hint.setObjectName("hint")
    win.lbl_profile_hint.setWordWrap(True)
    sec_profile.addWidget(win.lbl_profile_hint)
    if not COMPACT_UI:
        win.lbl_save_hint = QLabel("Auto-saves every ~45s. Re-build keeps install data.")
        win.lbl_save_hint.setObjectName("hint")
        win.lbl_save_hint.setWordWrap(True)
        sec_profile.addWidget(win.lbl_save_hint)

    sec_ready = section_group("Ready", v)
    win.lbl_field_score = QLabel("")
    win.lbl_field_score.setObjectName("tabContextLine")
    sec_ready.addWidget(win.lbl_field_score)
    win.lbl_field_checks = QLabel("")
    win.lbl_field_checks.setWordWrap(True)
    win.lbl_field_checks.setMaximumHeight(44 if COMPACT_UI else 16777215)
    win.lbl_field_checks.setStyleSheet("font-size:11px;line-height:1.35;color:#64748b;")
    sec_ready.addWidget(win.lbl_field_checks)
    row_ready = QHBoxLayout()
    b_refresh_ready = QPushButton("Refresh")
    b_refresh_ready.setObjectName("secondary")
    b_refresh_ready.clicked.connect(win._refresh_field_ready)
    row_ready.addWidget(b_refresh_ready)
    b_net = QPushButton("Test Wi‑Fi")
    b_net.setObjectName("secondary")
    b_net.clicked.connect(win._run_setup_network_test)
    row_ready.addWidget(b_net)
    row_ready.addStretch(1)
    if not SIMPLE_MODE:
        b_smoke = QPushButton("Smoke test")
        b_smoke.setObjectName("secondary")
        b_smoke.clicked.connect(win._run_smoke_test)
        row_ready.addWidget(b_smoke)
        b_checklist = QPushButton("Checklist")
        b_checklist.setObjectName("secondary")
        b_checklist.clicked.connect(win._show_setup_checklist)
        row_ready.addWidget(b_checklist)
        b_wiz = QPushButton("Wizard")
        b_wiz.setObjectName("secondary")
        b_wiz.clicked.connect(win._show_setup_wizard)
        row_ready.addWidget(b_wiz)
    sec_ready.addLayout(row_ready)

    sec_inv = section_group("Counter inventory", v, object_name="counterInventoryPanel")
    win.lbl_inventory_summary = QLabel("Serials update when you connect on Install/Pickup.")
    win.lbl_inventory_summary.setObjectName("hint")
    win.lbl_inventory_summary.setWordWrap(True)
    sec_inv.addWidget(win.lbl_inventory_summary)
    win.lbl_inventory_live = QLabel("Last USB read shows here.")
    win.lbl_inventory_live.setObjectName("counterVoltCheck")
    win.lbl_inventory_live.setWordWrap(True)
    apply_volt_check(win.lbl_inventory_live, None)
    sec_inv.addWidget(win.lbl_inventory_live)
    win.table_counter_inventory = QTableWidget(0, 6)
    win.table_counter_inventory.setHorizontalHeaderLabels(
        ["Serial", "Battery", "Unit ID", "Status", "Data", "Last check"])
    win.table_counter_inventory.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.Stretch)
    win.table_counter_inventory.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    win.table_counter_inventory.setSelectionBehavior(
        QTableWidget.SelectionBehavior.SelectRows)
    win.table_counter_inventory.setAlternatingRowColors(True)
    win.table_counter_inventory.setMaximumHeight(110 if COMPACT_UI else 180)
    sec_inv.addWidget(win.table_counter_inventory)

    sec_origin = section_group("Start point", v)
    win.lbl_origin = QLabel("")
    sec_origin.addWidget(win.lbl_origin)
    row_origin = QHBoxLayout()
    b_usb = QPushButton("USB GPS")
    b_usb.clicked.connect(win._origin_from_gps)
    row_origin.addWidget(b_usb)
    b_default = QPushButton("Save as my start")
    b_default.setObjectName("primary")
    b_default.setToolTip(
        "Save the lat/lon below as your start (use Search first to fill coordinates).")
    b_default.clicked.connect(win._save_default_home)
    win.btn_use_default = QPushButton("Use saved start")
    win.btn_use_default.setObjectName("secondary")
    win.btn_use_default.setToolTip("Restore your last saved home / start coordinates")
    win.btn_use_default.clicked.connect(win._load_default_home)
    row_origin.addWidget(b_default)
    row_origin.addWidget(win.btn_use_default)
    sec_origin.addLayout(row_origin)
    win.txt_address = QLineEdit()
    win.txt_address.setPlaceholderText("Address (online search)")
    win.txt_address.returnPressed.connect(win._origin_from_address)
    sec_origin.addWidget(win.txt_address)
    row_addr = QHBoxLayout()
    b_addr = QPushButton("Search")
    b_addr.clicked.connect(win._origin_from_address)
    win.btn_address = b_addr
    win.btn_saved_home = QPushButton("Use last address")
    win.btn_saved_home.setObjectName("secondary")
    win.btn_saved_home.setToolTip("Restore the last address you searched and saved")
    win.btn_saved_home.clicked.connect(win._use_saved_home)
    row_addr.addWidget(b_addr)
    row_addr.addWidget(win.btn_saved_home, 1)
    sec_origin.addLayout(row_addr)
    if not COMPACT_UI:
        win.lbl_address_hint = QLabel("")
        win.lbl_address_hint.setObjectName("hint")
        win.lbl_address_hint.setWordWrap(True)
        sec_origin.addWidget(win.lbl_address_hint)
    else:
        win.lbl_address_hint = QLabel("")
    row = QHBoxLayout()
    win.spin_lat = QDoubleSpinBox()
    win.spin_lat.setDecimals(5)
    win.spin_lat.setRange(-90, 90)
    win.spin_lat.setValue(win.state.home[0])
    win.spin_lon = QDoubleSpinBox()
    win.spin_lon.setDecimals(5)
    win.spin_lon.setRange(-180, 180)
    win.spin_lon.setValue(win.state.home[1])
    row.addWidget(win.spin_lat)
    row.addWidget(win.spin_lon)
    b_coords = QPushButton("Save coords")
    b_coords.setObjectName("secondary")
    b_coords.setToolTip("Save the lat/lon boxes as your start (same as Save as my start)")
    b_coords.clicked.connect(win._origin_from_coords)
    row.addWidget(b_coords)
    sec_origin.addLayout(row)

    sec_files = section_group("Files", v)
    row_files_btn = QHBoxLayout()
    b_excel = QPushButton("Excel/CSV")
    b_excel.clicked.connect(win._pick_excel)
    b_est = QPushButton(".EST maps")
    b_est.clicked.connect(win._pick_est)
    row_files_btn.addWidget(b_excel)
    row_files_btn.addWidget(b_est)
    sec_files.addLayout(row_files_btn)
    win.list_excel = QListWidget()
    win.list_excel.setMaximumHeight(40 if COMPACT_UI else 56)
    sec_files.addWidget(win.list_excel)
    win.list_est = QListWidget()
    win.list_est.setMaximumHeight(44 if COMPACT_UI else 64)
    sec_files.addWidget(win.list_est)
    row_files = QHBoxLayout()
    b_clear = QPushButton("Clear file lists")
    b_clear.setObjectName("secondary")
    b_clear.setToolTip("Remove Excel/.EST paths only — route and install data stay.")
    b_clear.clicked.connect(win._clear_files)
    b_demo = QPushButton("Demo")
    b_demo.setObjectName("secondary")
    b_demo.clicked.connect(win._load_demo_files)
    row_files.addWidget(b_clear)
    row_files.addWidget(b_demo)
    sec_files.addLayout(row_files)

    sec_build = section_group("Road map & route", v)
    row_map_dl = QHBoxLayout()
    b_basemap = QPushButton("Download California map")
    b_basemap.clicked.connect(win._download_basemap)
    win.btn_download_basemap = b_basemap
    row_map_dl.addWidget(b_basemap, 1)
    sec_build.addLayout(row_map_dl)
    row_roads = QHBoxLayout()
    b_roads = QPushButton("Download")
    b_roads.clicked.connect(win._download_roads)
    win.btn_download_roads = b_roads
    b_import_roads = QPushButton("Import .graphml")
    b_import_roads.setObjectName("secondary")
    b_import_roads.clicked.connect(win._import_roads)
    win.btn_import_roads = b_import_roads
    row_roads.addWidget(b_roads)
    row_roads.addWidget(b_import_roads, 1)
    sec_build.addLayout(row_roads)
    if not COMPACT_UI:
        win.lbl_roads_hint = QLabel(
            "Work Wi‑Fi may block download — import road_graph.graphml from home PC.")
        win.lbl_roads_hint.setObjectName("hint")
        win.lbl_roads_hint.setWordWrap(True)
        sec_build.addWidget(win.lbl_roads_hint)
    else:
        win.lbl_roads_hint = QLabel("")
    win.btn_build = QPushButton(BUILD_LABEL)
    win.btn_build.setObjectName("primary")
    win.btn_build.clicked.connect(win._build_route_from_uploads)
    sec_build.addWidget(win.btn_build)

    if COMPACT_UI:
        win.combo_port = QComboBox()
        win.combo_port.hide()
        win.lbl_offline = QLabel("")
        win.lbl_offline.hide()
        win._refresh_ports()
    else:
        sec_gps = section_group("Before you leave", v)
        win.combo_port = QComboBox()
        sec_gps.addWidget(win.combo_port)
        rowg = QHBoxLayout()
        b_refresh_ports = QPushButton("Ports")
        b_refresh_ports.setObjectName("secondary")
        b_refresh_ports.clicked.connect(win._refresh_ports)
        b_useport = QPushButton("Use port")
        b_useport.setObjectName("secondary")
        b_useport.clicked.connect(win._set_gps_port)
        rowg.addWidget(b_refresh_ports)
        rowg.addWidget(b_useport)
        sec_gps.addLayout(rowg)
        win._refresh_ports()
        win.lbl_offline = QLabel("")
        win.lbl_offline.setWordWrap(True)
        sec_gps.addWidget(win.lbl_offline)
        hint_mode = QLabel("Online / offline — top bar before you leave.")
        hint_mode.setObjectName("hint")
        hint_mode.setWordWrap(True)
        sec_gps.addWidget(hint_mode)

    return w
