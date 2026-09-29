"""Install tab — GPS grab, install capture (counter USB via TrafficViewer)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.paths import DIRECTIONS
from ui.simple_mode import COMPACT_UI
from ui.spacing import apply_card_layout, apply_grid
from ui.widgets import attach_more, more_body, numbered_section, page_column, page_with_footer, section_group


def build_install_page(win) -> QWidget:
    if COMPACT_UI:
        w, v, foot, _footer = page_with_footer()
    else:
        w, v = page_column()
        foot = v
    w.setObjectName("installPage")

    header = QFrame()
    header.setObjectName("installHeaderCompact" if COMPACT_UI else "installHeader")
    hv = QVBoxLayout(header)
    apply_card_layout(hv)
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

    lbl_prog = QLabel("Excel sites — OK / SKIP / GPS")
    lbl_prog.setObjectName("hint")
    win.list_install_progress = QListWidget()
    win.list_install_progress.setObjectName("installProgress")
    win.list_install_progress.setMaximumHeight(110 if COMPACT_UI else 150)
    win.list_install_progress.setToolTip(
        "Route progress by Excel sheet — tap a row to open that site. "
        "OK=installed, SKIP=skipped, GPS=grab saved.")
    win.list_install_progress.itemClicked.connect(win._install_progress_clicked)
    if COMPACT_UI:
        more_host, more_lay = more_body()
        more_lay.addWidget(lbl_prog)
        more_lay.addWidget(win.list_install_progress)
    else:
        more_host = None
        more_lay = v
        v.addWidget(lbl_prog)
        v.addWidget(win.list_install_progress)

    if COMPACT_UI:
        win.sec_compass = None
        win.lbl_compass_sub = QLabel("")
        win.lbl_direction_hint = QLabel("")
    else:
        sec_compass = section_group("Compass", v)
        win.lbl_compass = QLabel("Waiting for GPS heading…")
        win.lbl_compass.setObjectName("installCompass")
        sec_compass.addWidget(win.lbl_compass)
        win.lbl_compass_sub = QLabel("")
        win.lbl_compass_sub.setObjectName("hint")
        win.lbl_compass_sub.setWordWrap(True)
        sec_compass.addWidget(win.lbl_compass_sub)
        win.lbl_direction_hint = QLabel("")
        win.lbl_direction_hint.setObjectName("hint")
        win.lbl_direction_hint.setWordWrap(True)
        sec_compass.addWidget(win.lbl_direction_hint)
        row_comp = QHBoxLayout()
        b_comp_dir = QPushButton("From compass")
        b_comp_dir.setObjectName("secondary")
        b_comp_dir.clicked.connect(win._set_dir_from_compass)
        row_comp.addWidget(b_comp_dir, 1)
        sec_compass.addLayout(row_comp)

    if COMPACT_UI:
        sec_form, _ = numbered_section(1, "Site data", v)
    else:
        sec_form = section_group("Site data", v)
    win.txt_street = QLineEdit()
    win.txt_street.setPlaceholderText("Street name")
    win.txt_street.textChanged.connect(win._schedule_autosave)
    note_typed = getattr(win, "_note_street_typed", None)
    if note_typed is not None:
        win.txt_street.textChanged.connect(note_typed)
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
    win.txt_notes.setMaximumHeight(36 if COMPACT_UI else 72)
    win.txt_notes.textChanged.connect(win._schedule_autosave)
    if COMPACT_UI:
        more_lay.addWidget(win.txt_notes)
    else:
        sec_form.addWidget(win.txt_notes)
    # GPS / pin actions — 2-column grid so labels never truncate in the
    # narrow field panel (was a single cramped row: "ab G", "op p", "save").
    grid_grab = QGridLayout()
    apply_grid(grid_grab)
    grid_grab.setColumnStretch(0, 1)
    grid_grab.setColumnStretch(1, 1)

    b_grab = QPushButton("Grab GPS")
    b_grab.setObjectName("secondary")
    b_grab.setToolTip("Use USB GPS receiver at your current location")
    b_grab.clicked.connect(win._grab_gps_here)
    win.btn_manual_grab = QPushButton("Drop pin")
    win.btn_manual_grab.setObjectName("secondary")
    win.btn_manual_grab.setCheckable(True)
    win.btn_manual_grab.setToolTip(
        "Click the map to drop a pin for this site — GPS saves immediately (drag pin to adjust).")
    win.btn_manual_grab.clicked.connect(win._toggle_manual_grab)
    win.btn_confirm_pin = QPushButton("Re-save pin")
    win.btn_confirm_pin.setObjectName("secondary")
    win.btn_confirm_pin.setToolTip("Re-save orange pin position after dragging")
    win.btn_confirm_pin.clicked.connect(win._confirm_manual_grab_pin)
    win.btn_clear_gps = QPushButton("Clear GPS / pin")
    win.btn_clear_gps.setObjectName("secondary")
    win.btn_clear_gps.setToolTip("Remove saved GPS or manual pin for this site (fix accidental double grab)")
    win.btn_clear_gps.clicked.connect(win._clear_field_gps)
    if COMPACT_UI:
        b_comp_dir = QPushButton("Set direction")
        b_comp_dir.setObjectName("secondary")
        b_comp_dir.setToolTip("Set direction from compass heading")
        b_comp_dir.clicked.connect(win._set_dir_from_compass)
        grid_grab.addWidget(b_grab, 0, 0)
        grid_grab.addWidget(b_comp_dir, 0, 1)
        sec_form.addLayout(grid_grab)
        pin_grid = QGridLayout()
        apply_grid(pin_grid)
        pin_grid.setColumnStretch(0, 1)
        pin_grid.setColumnStretch(1, 1)
        pin_grid.addWidget(win.btn_manual_grab, 0, 0)
        pin_grid.addWidget(win.btn_confirm_pin, 0, 1)
        more_lay.addLayout(pin_grid)
        more_lay.addWidget(win.btn_clear_gps)
    else:
        grid_grab.addWidget(b_grab, 0, 0)
        grid_grab.addWidget(win.btn_manual_grab, 0, 1)
        grid_grab.addWidget(win.btn_confirm_pin, 1, 0, 1, 2)
        sec_form.addLayout(grid_grab)
        sec_form.addWidget(win.btn_clear_gps)

    win.lbl_grab = QLabel("")
    win.lbl_grab.setObjectName("hint")
    win.lbl_grab.setWordWrap(True)
    sec_form.addWidget(win.lbl_grab)

    win.lbl_install_checklist = QLabel("○ GPS / pin   ○ Serial #  (advisory)")
    win.lbl_install_checklist.setObjectName("installChecklist")
    win.lbl_install_checklist.setWordWrap(True)
    v.addWidget(win.lbl_install_checklist)
    if COMPACT_UI and more_host is not None:
        attach_more(v, more_host)

    row2 = QHBoxLayout()
    b_install = QPushButton("INSTALL  (I)")
    b_install.setObjectName("fieldPrimary")
    b_install.setMinimumHeight(44)
    b_install.clicked.connect(lambda: win._commit_install(True))
    b_skip = QPushButton("SKIP  (S)")
    b_skip.setObjectName("fieldSkip")
    b_skip.setMinimumHeight(44)
    b_skip.clicked.connect(lambda: win._commit_install(False))
    row2.addWidget(b_skip, 1)
    row2.addWidget(b_install, 2)

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
    foot.addLayout(row3)
    foot.addLayout(row2)
    if not COMPACT_UI:
        lbl_keys = QLabel("I install · S skip · G grab GPS · M drop pin · N/P prev/next")
        lbl_keys.setObjectName("hint")
        lbl_keys.setWordWrap(True)
        v.addWidget(lbl_keys)
        b_show = QPushButton("Show on map")
        b_show.setObjectName("secondary")
        b_show.clicked.connect(win._center_current)
        v.addWidget(b_show)
    return w
