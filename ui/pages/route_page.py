"""Route tab — drive, map, stop list."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.simple_mode import COMPACT_PAD, COMPACT_UI, SIMPLE_MODE
from ui.widgets import section_group


def build_route_page(win) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    pad = COMPACT_PAD if COMPACT_UI else 14
    v.setContentsMargins(pad, pad, pad, pad)
    v.setSpacing(8 if COMPACT_UI else 10)

    win.lbl_route_summary = QLabel("")
    win.lbl_route_summary.setObjectName("tabContextLine")
    win.lbl_route_summary.setWordWrap(True)
    v.addWidget(win.lbl_route_summary)

    win.lbl_route_stats = QLabel("")
    win.lbl_route_stats.hide()
    win.lbl_field_strip = QLabel("")
    win.lbl_field_strip.hide()

    win.lbl_pickup_reminder = QLabel("")
    win.lbl_pickup_reminder.setObjectName("pickupReminder")
    win.lbl_pickup_reminder.setWordWrap(True)
    win.lbl_pickup_reminder.hide()
    v.addWidget(win.lbl_pickup_reminder)

    win.lbl_drive_banner = QLabel("")
    win.lbl_drive_banner.setWordWrap(True)
    win.lbl_drive_banner.setObjectName("driveBanner")
    win.lbl_drive_banner.hide()
    v.addWidget(win.lbl_drive_banner)

    sec_drive = section_group("Navigate", v)
    win.btn_start = QPushButton("FOLLOW GPS")
    win.btn_start.setObjectName("go")
    win.btn_start.setToolTip("Follow mode pans the map with your GPS position.")
    win.btn_start.clicked.connect(win._toggle_drive)
    sec_drive.addWidget(win.btn_start)

    sec_pick_lay = section_group("Plan route", v)
    sec_pick = sec_pick_lay.parentWidget()
    win.lbl_pick_status = QLabel("Pick stop order on the map or in the popup.")
    win.lbl_pick_status.setObjectName("hint")
    win.lbl_pick_status.setWordWrap(True)
    sec_pick_lay.addWidget(win.lbl_pick_status)
    win.pick_combo_row = QWidget()
    win.pick_combo_row.hide()
    row_pick_site = QHBoxLayout(win.pick_combo_row)
    row_pick_site.setContentsMargins(0, 0, 0, 0)
    win.lbl_pick_slot = QLabel("Stop 1:")
    win.lbl_pick_slot.setMinimumWidth(52)
    win.combo_pick_site = QComboBox()
    win.combo_pick_site.setMinimumWidth(220)
    win.combo_pick_site.activated.connect(win._on_pick_combo_chosen)
    row_pick_site.addWidget(win.lbl_pick_slot)
    row_pick_site.addWidget(win.combo_pick_site, 1)
    sec_pick_lay.addWidget(win.pick_combo_row)
    row_pick = QHBoxLayout()
    win.btn_pick_auto = QPushButton("Auto-finish")
    win.btn_pick_auto.setObjectName("secondary")
    win.btn_pick_auto.clicked.connect(win._route_pick_auto_finish)
    win.btn_pick_auto.hide()
    win.btn_pick_clear = QPushButton("Clear")
    win.btn_pick_clear.setObjectName("secondary")
    win.btn_pick_clear.clicked.connect(win._route_pick_clear)
    win.btn_pick_apply = QPushButton("Apply route")
    win.btn_pick_apply.setObjectName("primary")
    win.btn_pick_apply.clicked.connect(win._route_pick_apply)
    row_pick.addWidget(win.btn_pick_auto)
    row_pick.addWidget(win.btn_pick_clear)
    row_pick.addWidget(win.btn_pick_apply)
    sec_pick_lay.addLayout(row_pick)
    win.btn_pick_order_win = QPushButton("Route order window")
    win.btn_pick_order_win.setObjectName("secondary")
    win.btn_pick_order_win.clicked.connect(win._show_route_pick_dialog)
    sec_pick_lay.addWidget(win.btn_pick_order_win)
    win.sec_pick = sec_pick
    if SIMPLE_MODE and sec_pick is not None:
        sec_pick.hide()

    sec_map_lay = section_group("Map", v)
    sec_map = sec_map_lay.parentWidget()
    row_map = QHBoxLayout()
    win.chk_show_segments = QCheckBox("Site lines")
    win.chk_show_segments.setChecked(False)
    win.chk_show_segments.stateChanged.connect(lambda: win._push_state())
    row_map.addWidget(win.chk_show_segments)
    b_fit = QPushButton("Zoom all")
    b_fit.setObjectName("secondary")
    b_fit.clicked.connect(lambda: win._push_state(fit=True))
    row_map.addWidget(b_fit)
    row_map.addStretch(1)
    sec_map_lay.addLayout(row_map)
    # Day filter lives in top bar (combo_day on MainWindow).

    sec_stops_lay = section_group("Stops", v, stretch=1)
    sec_stops = sec_stops_lay.parentWidget()
    win.list_route = QListWidget()
    win.list_route.setMinimumHeight(120 if COMPACT_UI else 160)
    win.list_route.itemClicked.connect(win._route_item_clicked)
    sec_stops_lay.addWidget(win.list_route, 1)

    row_actions = QHBoxLayout()
    b_up = QPushButton("↑")
    b_up.setObjectName("secondary")
    b_up.setToolTip("Move stop up")
    b_up.clicked.connect(lambda: win._nudge_stop(-1))
    b_dn = QPushButton("↓")
    b_dn.setObjectName("secondary")
    b_dn.setToolTip("Move stop down")
    b_dn.clicked.connect(lambda: win._nudge_stop(1))
    b_retrace = QPushButton("Re-trace")
    b_retrace.setObjectName("secondary")
    b_retrace.setToolTip("Re-trace route on streets")
    b_retrace.clicked.connect(win._retrace_route_only)
    b_reopt = QPushButton("Change order…" if SIMPLE_MODE else "Re-optimize")
    b_reopt.setObjectName("secondary")
    b_reopt.clicked.connect(win._reoptimize)
    b_reset = QPushButton("Clear shift…")
    b_reset.setObjectName("secondary")
    b_reset.clicked.connect(win._reset_route)
    row_actions.addWidget(b_up)
    row_actions.addWidget(b_dn)
    row_actions.addWidget(b_retrace)
    row_actions.addWidget(b_reopt, 1)
    row_actions.addWidget(b_reset)
    sec_stops_lay.addLayout(row_actions)

    phone_heading = "Route HTML" if SIMPLE_MODE else "Phone links"
    sec_phone_lay = section_group(phone_heading, v)
    sec_phone = sec_phone_lay.parentWidget()
    row_phone = QHBoxLayout()
    b_install_links = QPushButton(
        "Save HTML route (site order)" if SIMPLE_MODE else "Install links",
    )
    b_install_links.setObjectName("secondary")
    b_install_links.setToolTip(
        "Save an HTML page with one Google Maps link per stop in route order.",
    )
    b_install_links.clicked.connect(win._save_install_nav_links)
    b_pickup_links = QPushButton(
        "Save HTML pickup order" if SIMPLE_MODE else "Pickup links",
    )
    b_pickup_links.setObjectName("secondary")
    b_pickup_links.setToolTip("Save HTML with one link per installed site, oldest first.")
    b_pickup_links.clicked.connect(win._save_pickup_nav_links)
    row_phone.addWidget(b_install_links)
    row_phone.addWidget(b_pickup_links)
    sec_phone_lay.addLayout(row_phone)

    win.lbl_stat_stops = win.lbl_stat_miles = win.lbl_stat_kind = None
    win._route_fold_boxes = [sec_pick, sec_map, sec_stops]
    if sec_phone is not None:
        win._route_fold_boxes.append(sec_phone)
    return w
