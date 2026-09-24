"""Setup tab — files, home, road map, build."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.hardware_profile import is_work_laptop
from ui.simple_mode import BUILD_LABEL, COMPACT_UI, SIMPLE_MODE
from ui.widgets import (
    WorkflowStrip,
    attach_more,
    button_row,
    button_stack,
    more_body,
    numbered_section,
    page_column,
    page_with_footer,
    section_group,
    section_heading,
    step_block,
)


def build_setup_page(win) -> QWidget:
    footer = None
    if SIMPLE_MODE:
        w, v, foot, footer = page_with_footer()
        win._setup_footer = footer
        footer.hide()
    else:
        w, v = page_column()
        foot = v

    more_lay = None
    if SIMPLE_MODE:
        win._setup_more_open = False

    if not SIMPLE_MODE:
        win.workflow_strip = WorkflowStrip()
        v.addWidget(win.workflow_strip)
    else:
        win.workflow_strip = None
        win._setup_step_headers: dict[str, QLabel] = {}

    # --- Profile (desk tools, no step number) ---
    if SIMPLE_MODE:
        more_host, more_lay = more_body()
        win._setup_more_body = more_host
        profile_host = more_lay
    else:
        more_host = None
        profile_host = v
    section_heading("Profile", profile_host)
    win.txt_profile = QLineEdit(win.state.profile)
    win.txt_profile.setPlaceholderText("DEFAULT, WEEK9…")
    win.txt_profile.returnPressed.connect(lambda: win._switch_profile())
    profile_host.addWidget(win.txt_profile)
    b_prof = QPushButton("Load")
    b_prof.setObjectName("secondary")
    b_prof.clicked.connect(lambda: win._switch_profile())
    b_save_as = QPushButton("Save as…")
    b_save_as.setObjectName("secondary")
    b_save_as.setToolTip("Save current shift under a new profile name")
    b_save_as.clicked.connect(win._save_profile_as)
    b_save_now = QPushButton("Save")
    b_save_now.setObjectName("secondary")
    b_save_now.setToolTip("Save progress now")
    b_save_now.clicked.connect(win._save_shift_now)
    button_row(profile_host, b_prof, b_save_as, b_save_now)
    b_clear_shift = QPushButton("Clear shift")
    b_clear_shift.setObjectName("secondary")
    b_clear_shift.setToolTip(
        "Remove sites, route, and install/pickup progress for this profile. "
        "Excel/.EST file lists stay unless you clear them below.")
    b_clear_shift.clicked.connect(win._reset_route)
    win.btn_clear_shift = b_clear_shift
    b_start_fresh = QPushButton("Start fresh")
    b_start_fresh.setObjectName("secondary")
    b_start_fresh.setToolTip("Clear shift data and Excel/.EST file lists — empty map on next launch.")
    b_start_fresh.clicked.connect(win._start_fresh_profile)
    win.btn_start_fresh = b_start_fresh
    button_row(profile_host, b_clear_shift, b_start_fresh)
    if not COMPACT_UI:
        win.lbl_profile_hint = QLabel(
            "Sites on the map at launch = saved shift for this profile (e.g. DEFAULT). "
            "Use Clear shift data to wipe pins and route.")
        win.lbl_profile_hint.setObjectName("hint")
        win.lbl_profile_hint.setWordWrap(True)
        profile_host.addWidget(win.lbl_profile_hint)
        win.lbl_save_hint = QLabel("Auto-saves every ~45s. Re-build keeps install data.")
        win.lbl_save_hint.setObjectName("hint")
        win.lbl_save_hint.setWordWrap(True)
        profile_host.addWidget(win.lbl_save_hint)
    else:
        win.lbl_profile_hint = QLabel("")
        win.lbl_save_hint = QLabel("")

    # --- Ready status ---
    section_heading("Ready", v)
    win.lbl_field_score = QLabel("")
    win.lbl_field_score.setObjectName("tabContextLine")
    v.addWidget(win.lbl_field_score)
    win.lbl_field_checks = QLabel("")
    win.lbl_field_checks.setObjectName("fieldChecks")
    win.lbl_field_checks.setWordWrap(True)
    v.addWidget(win.lbl_field_checks)
    b_refresh_ready = QPushButton("Refresh")
    b_refresh_ready.setObjectName("secondary")
    b_refresh_ready.clicked.connect(win._refresh_field_ready)
    b_net = QPushButton("Test Wi‑Fi")
    b_net.setObjectName("secondary")
    b_net.clicked.connect(win._run_setup_network_test)
    win.btn_test_wifi = b_net
    row_ready_btns: list[QPushButton] = [b_refresh_ready, b_net]
    if not SIMPLE_MODE:
        b_smoke = QPushButton("Smoke test")
        b_smoke.setObjectName("secondary")
        b_smoke.clicked.connect(win._run_smoke_test)
        b_checklist = QPushButton("Checklist")
        b_checklist.setObjectName("secondary")
        b_checklist.clicked.connect(win._show_setup_checklist)
        b_wiz = QPushButton("Wizard")
        b_wiz.setObjectName("secondary")
        b_wiz.clicked.connect(win._show_setup_wizard)
        row_ready_btns.extend([b_smoke, b_checklist, b_wiz])
    ready_host = more_lay if SIMPLE_MODE else v
    button_row(ready_host, *row_ready_btns)

    # --- 1. Start point ---
    if SIMPLE_MODE:
        win._setup_step_blocks = {}
        start_box, start_lay = step_block(v)
        win._setup_step_blocks["start"] = start_box
        sec_origin, hdr_start = numbered_section(1, "Start", start_lay, step_id="start")
        win._setup_step_headers["start"] = hdr_start
        extra_start = more_lay
    else:
        sec_origin = section_group("Start point", v)
        extra_start = sec_origin
    win.lbl_origin = QLabel("")
    win.lbl_origin.setWordWrap(True)
    sec_origin.addWidget(win.lbl_origin)
    b_usb = QPushButton("USB GPS")
    b_usb.clicked.connect(win._origin_from_gps)
    button_stack(sec_origin, b_usb)
    win.txt_address = QLineEdit()
    win.txt_address.setPlaceholderText("Address (online search)")
    win.txt_address.returnPressed.connect(win._origin_from_address)
    sec_origin.addWidget(win.txt_address)
    b_addr = QPushButton("Search")
    b_addr.clicked.connect(win._origin_from_address)
    win.btn_address = b_addr
    button_stack(sec_origin, b_addr)
    b_default = QPushButton("Save start")
    b_default.setObjectName("primary")
    b_default.setToolTip(
        "Save the lat/lon below as your start (use Search first to fill coordinates).")
    b_default.clicked.connect(win._save_default_home)
    win.btn_use_default = QPushButton("Use saved")
    win.btn_use_default.setObjectName("secondary")
    win.btn_use_default.setToolTip("Restore your last saved home / start coordinates")
    win.btn_use_default.clicked.connect(win._load_default_home)
    win.btn_saved_home = QPushButton("Last address")
    win.btn_saved_home.setObjectName("secondary")
    win.btn_saved_home.setToolTip("Restore the last address you searched and saved")
    win.btn_saved_home.clicked.connect(win._use_saved_home)
    if SIMPLE_MODE:
        button_stack(extra_start, b_default, win.btn_use_default, win.btn_saved_home)
    else:
        button_row(extra_start, b_default, win.btn_use_default, win.btn_saved_home)
    if not COMPACT_UI:
        win.lbl_address_hint = QLabel("")
        win.lbl_address_hint.setObjectName("hint")
        win.lbl_address_hint.setWordWrap(True)
        sec_origin.addWidget(win.lbl_address_hint)
    else:
        win.lbl_address_hint = QLabel("")
    win.spin_lat = QDoubleSpinBox()
    win.spin_lat.setDecimals(5)
    win.spin_lat.setRange(-90, 90)
    win.spin_lat.setValue(win.state.home[0])
    win.spin_lon = QDoubleSpinBox()
    win.spin_lon.setDecimals(5)
    win.spin_lon.setRange(-180, 180)
    win.spin_lon.setValue(win.state.home[1])
    b_coords = QPushButton("Save coords")
    b_coords.setObjectName("secondary")
    b_coords.setToolTip("Save the lat/lon boxes as your start (same as Save start)")
    b_coords.clicked.connect(win._origin_from_coords)
    if SIMPLE_MODE:
        button_row(extra_start, win.spin_lat, win.spin_lon)
        button_stack(extra_start, b_coords)
    else:
        button_row(extra_start, win.spin_lat, win.spin_lon, b_coords)

    # --- 2. Files ---
    if SIMPLE_MODE:
        files_box, files_lay = step_block(v)
        win._setup_step_blocks["files"] = files_box
        files_box.hide()
        sec_files, hdr_files = numbered_section(2, "Files", files_lay, step_id="files")
        win._setup_step_headers["files"] = hdr_files
        files_extra = more_lay
    else:
        sec_files = section_group("Files", v)
        files_extra = sec_files
    b_excel = QPushButton("Excel/CSV")
    b_excel.clicked.connect(win._pick_excel)
    b_est = QPushButton(".EST maps")
    b_est.clicked.connect(win._pick_est)
    b_clear = QPushButton("Clear lists")
    b_clear.setObjectName("secondary")
    b_clear.setToolTip("Remove Excel/.EST paths only — route and install data stay.")
    b_clear.clicked.connect(win._clear_files)
    if SIMPLE_MODE:
        button_stack(sec_files, b_excel, b_est)
        button_stack(files_extra, b_clear)
    else:
        button_row(sec_files, b_excel, b_est)
        button_row(files_extra, b_clear)
    _list_h = 52 if is_work_laptop() else (40 if COMPACT_UI else 56)
    win.list_excel = QListWidget()
    win.list_excel.setMaximumHeight(_list_h)
    sec_files.addWidget(win.list_excel)
    win.list_est = QListWidget()
    win.list_est.setMaximumHeight(_list_h + 4)
    sec_files.addWidget(win.list_est)

    # --- 3. Road map ---
    if SIMPLE_MODE:
        roads_box, roads_lay = step_block(v)
        win._setup_step_blocks["roads"] = roads_box
        roads_box.hide()
        sec_build, hdr_roads = numbered_section(3, "Road map", roads_lay, step_id="roads")
        win._setup_step_headers["roads"] = hdr_roads
    else:
        sec_build = section_group("Road map & route", v)
    b_basemap = QPushButton("CA map")
    b_basemap.clicked.connect(win._download_basemap)
    win.btn_download_basemap = b_basemap
    b_roads = QPushButton("Download roads")
    b_roads.clicked.connect(win._download_roads)
    win.btn_download_roads = b_roads
    b_import_roads = QPushButton("Import .graphml")
    b_import_roads.setObjectName("secondary")
    b_import_roads.clicked.connect(win._import_roads)
    win.btn_import_roads = b_import_roads
    if SIMPLE_MODE:
        button_stack(sec_build, b_basemap, b_roads, b_import_roads)
    else:
        button_row(sec_build, b_basemap, b_roads, b_import_roads)
    if not COMPACT_UI:
        win.lbl_roads_hint = QLabel(
            "Work Wi‑Fi may block download — import road_graph.graphml from home PC.")
        win.lbl_roads_hint.setObjectName("hint")
        win.lbl_roads_hint.setWordWrap(True)
        sec_build.addWidget(win.lbl_roads_hint)
    else:
        win.lbl_roads_hint = QLabel(
            "Work Wi‑Fi may block road download — import road_graph.graphml from home PC.")
        win.lbl_roads_hint.setObjectName("hint")
        win.lbl_roads_hint.setWordWrap(True)
        sec_build.addWidget(win.lbl_roads_hint)

    # --- 4. Build route ---
    if SIMPLE_MODE:
        build_box, build_lay = step_block(v)
        win._setup_step_blocks["build"] = build_box
        build_box.hide()
        sec_route, hdr_build = numbered_section(4, "Build route", build_lay, step_id="build")
        win._setup_step_headers["build"] = hdr_build
    else:
        sec_route = sec_build
    win.btn_build = QPushButton(BUILD_LABEL)
    win.btn_build.setObjectName("primary")
    win.btn_build.setToolTip(
        "Opens the map so you tap stop order: blue dot = begin, red dot = end. "
        "Two .EST maps: pick Day 1, then Day 2. Optional Merge after both are picked. "
        "Writes HTML install lists (merged + one file per day).")
    win.btn_build.clicked.connect(win._build_route_from_uploads)
    win.btn_build.setMinimumHeight(44)
    button_row(sec_route, win.btn_build)

    if SIMPLE_MODE and more_host is not None:
        def _more_toggled(checked: bool) -> None:
            win._setup_more_open = checked
            refresh = getattr(win, "_refresh_workflow_strip", None)
            if callable(refresh):
                refresh()
                return
            for sid, block in getattr(win, "_setup_step_blocks", {}).items():
                block.setVisible(checked or sid == "start")

        attach_more(v, more_host, _more_toggled)
        win.btn_setup_go_offline = QPushButton("Go offline")
        win.btn_setup_go_offline.setObjectName("primary")
        win.btn_setup_go_offline.setMinimumHeight(44)
        win.btn_setup_go_offline.clicked.connect(lambda: win._on_mode_offline())
        win.btn_setup_go_offline.hide()
        foot.addWidget(win.btn_setup_go_offline)

    if COMPACT_UI:
        win.combo_port = QComboBox()
        win.combo_port.hide()
        win.lbl_offline = QLabel("")
        win.lbl_offline.setObjectName("offlineHint")
        win.lbl_offline.setWordWrap(True)
        v.addWidget(win.lbl_offline)
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
