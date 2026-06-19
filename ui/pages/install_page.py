"""Install tab — GPS grab, PicoCount, install capture."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.counter_ui import apply_counter_status
from ui.paths import DIRECTIONS
from ui.simple_mode import COMPACT_UI, COMPACT_PAD
from ui.widgets import section_group


def build_install_page(win) -> QWidget:
    w = QWidget()
    w.setObjectName("installPage")
    v = QVBoxLayout(w)
    pad = COMPACT_PAD if COMPACT_UI else 12
    v.setContentsMargins(pad, pad, pad, pad)
    v.setSpacing(6 if COMPACT_UI else 10)

    header = QFrame()
    header.setObjectName("installHeaderCompact" if COMPACT_UI else "installHeader")
    hv = QVBoxLayout(header)
    hv.setContentsMargins(10, 8, 10, 8 if COMPACT_UI else 12)
    hv.setSpacing(2)
    win.lbl_install_title = QLabel("No stop selected.")
    win.lbl_install_title.setObjectName("installTitle")
    win.lbl_install_title.setWordWrap(True)
    hv.addWidget(win.lbl_install_title)
    win.lbl_install_prog = QLabel("")
    win.lbl_install_prog.setObjectName("installSub")
    win.lbl_install_prog.setWordWrap(True)
    hv.addWidget(win.lbl_install_prog)
    win.lbl_compass = QLabel("")
    win.lbl_compass.setObjectName("installCompass")
    win.lbl_compass.setWordWrap(True)
    if COMPACT_UI:
        hv.addWidget(win.lbl_compass)
    win.lbl_cross_hint = QLabel("")
    win.lbl_cross_hint.setObjectName("hint")
    win.lbl_cross_hint.setWordWrap(True)
    if COMPACT_UI:
        win.lbl_cross_hint.hide()
    else:
        hv.addWidget(win.lbl_cross_hint)
    win.lbl_street_warn = QLabel("")
    win.lbl_street_warn.setObjectName("installWarn")
    win.lbl_street_warn.setWordWrap(True)
    win.lbl_street_warn.hide()
    hv.addWidget(win.lbl_street_warn)
    v.addWidget(header)

    sec_compass = section_group("Compass", v)
    if not COMPACT_UI:
        win.lbl_compass = QLabel("Waiting for GPS heading…")
        win.lbl_compass.setObjectName("installCompass")
        sec_compass.addWidget(win.lbl_compass)
    win.lbl_compass_sub = QLabel("")
    win.lbl_compass_sub.setObjectName("hint")
    if not COMPACT_UI:
        win.lbl_compass_sub.setWordWrap(True)
        sec_compass.addWidget(win.lbl_compass_sub)
    win.lbl_direction_hint = QLabel("")
    win.lbl_direction_hint.setObjectName("hint")
    if not COMPACT_UI:
        win.lbl_direction_hint.setWordWrap(True)
        sec_compass.addWidget(win.lbl_direction_hint)
        row_comp = QHBoxLayout()
        b_comp_dir = QPushButton("From compass")
        b_comp_dir.setObjectName("secondary")
        b_comp_dir.clicked.connect(win._set_dir_from_compass)
        row_comp.addWidget(b_comp_dir, 1)
        sec_compass.addLayout(row_comp)
    elif COMPACT_UI:
        win.sec_compass = sec_compass.parentWidget()
        win.sec_compass.hide()

    sec_counter = section_group("PicoCount", v, object_name="counterPanel")
    win.counter_panel = sec_counter.parentWidget()
    win.lbl_counter_connected = QLabel("● CONNECTED")
    win.lbl_counter_connected.setObjectName("counterConnectedPill")
    win.lbl_counter_connected.hide()
    if not COMPACT_UI:
        sec_counter.addWidget(win.lbl_counter_connected)
    row_cp = QHBoxLayout()
    row_cp.addWidget(QLabel("Port"))
    win.combo_counter_port = QComboBox()
    win.combo_counter_port.setMinimumWidth(72)
    row_cp.addWidget(win.combo_counter_port, 1)
    win.btn_counter_refresh = QPushButton("Refresh")
    win.btn_counter_refresh.setObjectName("secondary")
    win.btn_counter_refresh.clicked.connect(win._counter_refresh_and_connect)
    row_cp.addWidget(win.btn_counter_refresh)
    sec_counter.addLayout(row_cp)
    win.lbl_counter_status = QLabel("Plug USB cable → Refresh")
    win.lbl_counter_status.setObjectName(
        "counterStatusCompact" if COMPACT_UI else "counterStatus")
    win.lbl_counter_status.setWordWrap(True)
    sec_counter.addWidget(win.lbl_counter_status)
    win.lbl_counter_unit = QLabel("")
    win.lbl_counter_unit.setObjectName("hint")
    if not COMPACT_UI:
        win.lbl_counter_unit.setWordWrap(True)
        sec_counter.addWidget(win.lbl_counter_unit)
    win.lbl_counter_data = QLabel("")
    win.lbl_counter_data.setObjectName("counterData")
    win.lbl_counter_data.setWordWrap(True)
    sec_counter.addWidget(win.lbl_counter_data)
    row_cnt = QHBoxLayout()
    win.btn_counter_autoname = QPushButton("Auto-name")
    win.btn_counter_autoname.setObjectName("secondary")
    win.btn_counter_autoname.setToolTip("Unit ID only (Site# + n/e + c1b)")
    win.btn_counter_autoname.clicked.connect(win._counter_autoname)
    if not COMPACT_UI:
        row_cnt.addWidget(win.btn_counter_autoname)
    win.btn_counter_clear = QPushButton("Clear counter")
    win.btn_counter_clear.setObjectName("primary")
    win.btn_counter_clear.setToolTip("Zero memory + set Unit ID for this site")
    win.btn_counter_clear.clicked.connect(win._counter_clear_configure)
    row_cnt.addWidget(win.btn_counter_clear)
    sec_counter.addLayout(row_cnt)
    win._counter_list_ports()
    apply_counter_status(
        win.lbl_counter_status, "idle", "Plug USB cable → Refresh")

    sec_form = section_group("Site data", v)
    win.txt_street = QLineEdit()
    win.txt_street.setPlaceholderText("Street name")
    win.txt_street.textChanged.connect(win._schedule_autosave)
    sec_form.addWidget(win.txt_street)
    row = QHBoxLayout()
    win.combo_dir = QComboBox()
    win.combo_dir.addItems(DIRECTIONS)
    win.combo_dir.currentTextChanged.connect(win._on_install_dir_changed)
    win.spin_lanes = QSpinBox()
    win.spin_lanes.setRange(1, 20)
    win.spin_lanes.setValue(2)
    win.spin_lanes.valueChanged.connect(lambda *_: win._schedule_autosave())
    win.txt_serial = QLineEdit()
    win.txt_serial.setPlaceholderText("Serial #")
    win.txt_serial.textChanged.connect(win._schedule_autosave)
    win.txt_serial.textChanged.connect(lambda *_: win._refresh_install_checklist())
    row.addWidget(QLabel("Dir"))
    row.addWidget(win.combo_dir, 1)
    row.addWidget(QLabel("Ln"))
    row.addWidget(win.spin_lanes)
    row.addWidget(win.txt_serial, 2)
    sec_form.addLayout(row)
    win.txt_notes = QPlainTextEdit()
    win.txt_notes.setPlaceholderText("Field notes (optional)")
    win.txt_notes.setMaximumHeight(48 if COMPACT_UI else 72)
    win.txt_notes.textChanged.connect(win._schedule_autosave)
    sec_form.addWidget(win.txt_notes)
    row_grab = QHBoxLayout()
    b_grab = QPushButton("Grab GPS")
    b_grab.setObjectName("secondary")
    b_grab.setToolTip("Use USB GPS receiver at your current location")
    b_grab.clicked.connect(win._grab_gps_here)
    row_grab.addWidget(b_grab)
    win.btn_manual_grab = QPushButton("Manual Grab")
    win.btn_manual_grab.setObjectName("secondary")
    win.btn_manual_grab.setCheckable(True)
    win.btn_manual_grab.setToolTip(
        "Zoom to this site, then click the street on the map for install position")
    win.btn_manual_grab.clicked.connect(win._toggle_manual_grab)
    row_grab.addWidget(win.btn_manual_grab)
    if COMPACT_UI:
        b_comp_dir = QPushButton("Dir ○")
        b_comp_dir.setObjectName("secondary")
        b_comp_dir.setToolTip("Set direction from compass heading")
        b_comp_dir.clicked.connect(win._set_dir_from_compass)
        row_grab.addWidget(b_comp_dir)
    win.lbl_grab = QLabel("")
    win.lbl_grab.setObjectName("hint")
    row_grab.addWidget(win.lbl_grab, 1)
    sec_form.addLayout(row_grab)

    win.lbl_install_checklist = QLabel("○ GPS   ○ Cleared   ○ Serial")
    win.lbl_install_checklist.setObjectName("installChecklist")
    win.lbl_install_checklist.setWordWrap(True)
    v.addWidget(win.lbl_install_checklist)

    row2 = QHBoxLayout()
    b_install = QPushButton("INSTALL  (I)")
    b_install.setObjectName("fieldPrimary")
    b_install.clicked.connect(lambda: win._commit_install(True))
    b_skip = QPushButton("SKIP  (S)")
    b_skip.setObjectName("fieldSkip")
    b_skip.clicked.connect(lambda: win._commit_install(False))
    row2.addWidget(b_install, 2)
    row2.addWidget(b_skip, 1)
    v.addLayout(row2)

    row3 = QHBoxLayout()
    win.btn_undo_install = QPushButton("Undo")
    win.btn_undo_install.setObjectName("secondary")
    win.btn_undo_install.setEnabled(False)
    win.btn_undo_install.clicked.connect(win._undo_last_action)
    b_prev = QPushButton("← Prev")
    b_prev.setObjectName("secondary")
    b_prev.clicked.connect(lambda: win._nav_install(-1))
    b_next = QPushButton("Next →")
    b_next.setObjectName("secondary")
    b_next.clicked.connect(lambda: win._nav_install(1))
    row3.addWidget(win.btn_undo_install)
    row3.addWidget(b_prev, 1)
    row3.addWidget(b_next, 1)
    v.addLayout(row3)
    if not COMPACT_UI:
        lbl_keys = QLabel("I install · S skip · G grab GPS · M manual map grab · N/P prev/next")
        lbl_keys.setObjectName("hint")
        lbl_keys.setWordWrap(True)
        v.addWidget(lbl_keys)
        b_show = QPushButton("Show on map")
        b_show.setObjectName("secondary")
        b_show.clicked.connect(win._center_current)
        v.addWidget(b_show)
    return w
