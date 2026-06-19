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

from ui.simple_mode import COMPACT_UI, COMPACT_PAD, SIMPLE_MODE
from ui.widgets import section_group, stat_card


def build_route_page(win) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    pad = COMPACT_PAD if COMPACT_UI else 14
    v.setContentsMargins(pad, pad, pad, pad)
    v.setSpacing(6 if COMPACT_UI else 10)

    if COMPACT_UI:
        win.lbl_route_summary = QLabel("")
        win.lbl_route_summary.setObjectName("tabContextLine")
        win.lbl_route_summary.setWordWrap(True)
        v.addWidget(win.lbl_route_summary)
        stats_row = None
        win.lbl_stat_stops = win.lbl_stat_miles = win.lbl_stat_kind = None
    else:
        stats_row = QHBoxLayout()
        stats_row.setSpacing(8)
        card_stops, win.lbl_stat_stops = stat_card("Stops", "0")
        card_miles, win.lbl_stat_miles = stat_card("Miles", "—")
        card_kind, win.lbl_stat_kind = stat_card("Routing", "—")
        stats_row.addWidget(card_stops, 1)
        stats_row.addWidget(card_miles, 1)
        stats_row.addWidget(card_kind, 1)
        v.addLayout(stats_row)
        win.lbl_route_summary = QLabel("")
        win.lbl_route_summary.setObjectName("hint")
        win.lbl_route_summary.setWordWrap(True)
        win.lbl_route_summary.setStyleSheet("font-weight:700;font-size:13px;color:#0f2744;")
        v.addWidget(win.lbl_route_summary)

    win.lbl_route_stats = QLabel("")
    win.lbl_route_stats.hide()
    win.lbl_field_strip = QLabel("")
    if COMPACT_UI:
        win.lbl_field_strip.hide()
    else:
        win.lbl_field_strip.setStyleSheet("font-size:12px;color:#475569;")
        v.addWidget(win.lbl_field_strip)

    win.lbl_pickup_reminder = QLabel("")
    win.lbl_pickup_reminder.setObjectName("pickupReminder")
    win.lbl_pickup_reminder.setWordWrap(True)
    win.lbl_pickup_reminder.hide()
    v.addWidget(win.lbl_pickup_reminder)

    win.lbl_drive_banner = QLabel("")
    win.lbl_drive_banner.setWordWrap(True)
    win.lbl_drive_banner.setStyleSheet(
        "background:#e3f2fd;border:1px solid #90caf9;border-radius:8px;"
        f"padding:{8 if COMPACT_UI else 12}px;font-weight:800;"
        f"font-size:{13 if COMPACT_UI else 15}px;color:#0d47a1;")
    win.lbl_drive_banner.hide()
    v.addWidget(win.lbl_drive_banner)

    sec_drive = section_group("Navigate", v)
    win.btn_start = QPushButton("FOLLOW GPS")
    win.btn_start.setObjectName("go")
    win.btn_start.setToolTip(
        "Follow mode pans the map with your GPS position.")
    win.btn_start.clicked.connect(win._toggle_drive)
    sec_drive.addWidget(win.btn_start)
    if not COMPACT_UI:
        hint_drive = QLabel(
            "Tap FOLLOW GPS to pan the map with you while driving.")
        hint_drive.setObjectName("hint")
        hint_drive.setWordWrap(True)
        sec_drive.addWidget(hint_drive)

    sec_pick_lay = section_group("Plan route (pick order)", v)
    sec_pick = sec_pick_lay.parentWidget()
    win.lbl_pick_status = QLabel(
        "Click sites on the map in order — blue begin or red end. Your list shows in the popup.")
    win.lbl_pick_status.setObjectName("hint")
    win.lbl_pick_status.setWordWrap(True)
    sec_pick_lay.addWidget(win.lbl_pick_status)
    win.pick_combo_row = QWidget()
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
    win.btn_pick_auto = QPushButton("Auto-finish rest")
    win.btn_pick_auto.setObjectName("secondary")
    win.btn_pick_auto.clicked.connect(win._route_pick_auto_finish)
    win.btn_pick_auto.hide()
    win.btn_pick_clear = QPushButton("Clear picks")
    win.btn_pick_clear.setObjectName("secondary")
    win.btn_pick_clear.clicked.connect(win._route_pick_clear)
    win.btn_pick_apply = QPushButton("Apply route")
    win.btn_pick_apply.setObjectName("primary")
    win.btn_pick_apply.clicked.connect(win._route_pick_apply)
    row_pick.addWidget(win.btn_pick_auto)
    row_pick.addWidget(win.btn_pick_clear)
    row_pick.addWidget(win.btn_pick_apply)
    sec_pick_lay.addLayout(row_pick)
    win.btn_pick_order_win = QPushButton("Show route order window")
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
    if not COMPACT_UI:
        b_recover = QPushButton("Recover map (blank canvas)")
        b_recover.setObjectName("secondary")
        b_recover.clicked.connect(win._recover_map)
        row_map.addWidget(b_recover)
    sec_map_lay.addLayout(row_map)
    if not COMPACT_UI:
        row_day = QHBoxLayout()
        row_day.addWidget(QLabel("Map filter:"))
        win.combo_day = QComboBox()
        win.combo_day.currentTextChanged.connect(win._on_day_filter_changed)
        row_day.addWidget(win.combo_day, 1)
        sec_map_lay.addLayout(row_day)
    else:
        win.combo_day = QComboBox()
        win.combo_day.currentTextChanged.connect(win._on_day_filter_changed)
        win.combo_day.hide()

    sec_stops_lay = section_group("Stops", v, stretch=0)
    sec_stops = sec_stops_lay.parentWidget()
    win.list_route = QListWidget()
    win.list_route.setMaximumHeight(100 if COMPACT_UI else 16777215)
    win.list_route.itemClicked.connect(win._route_item_clicked)
    sec_stops_lay.addWidget(win.list_route)

    row_nudge = QHBoxLayout()
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
    row_nudge.addWidget(b_up)
    row_nudge.addWidget(b_dn)
    row_nudge.addWidget(b_retrace, 1)
    v.addLayout(row_nudge)

    sec_phone_lay = section_group("Phone navigation (Google Maps)", v)
    sec_phone = sec_phone_lay.parentWidget()
    hint_phone = QLabel(
        "Save an HTML page of tap-to-drive links. Install = route order; "
        "Pickup = order sites were installed. Phone needs Wi‑Fi or cellular for Maps.")
    hint_phone.setObjectName("hint")
    hint_phone.setWordWrap(True)
    sec_phone_lay.addWidget(hint_phone)
    row_phone = QHBoxLayout()
    b_install_links = QPushButton("Install links page")
    b_install_links.setObjectName("secondary")
    b_install_links.setToolTip("One Google Maps link per stop in route visit order.")
    b_install_links.clicked.connect(win._save_install_nav_links)
    b_pickup_links = QPushButton("Pickup links page")
    b_pickup_links.setObjectName("secondary")
    b_pickup_links.setToolTip("One link per installed site, oldest install first.")
    b_pickup_links.clicked.connect(win._save_pickup_nav_links)
    row_phone.addWidget(b_install_links)
    row_phone.addWidget(b_pickup_links)
    sec_phone_lay.addLayout(row_phone)

    row_actions = QHBoxLayout()
    b_reopt = QPushButton("Change order…" if SIMPLE_MODE else "Re-optimize")
    b_reopt.setObjectName("secondary")
    b_reopt.clicked.connect(win._reoptimize)
    row_actions.addWidget(b_reopt)
    b_reset = QPushButton("Clear shift…")
    b_reset.setObjectName("secondary")
    b_reset.clicked.connect(win._reset_route)
    row_actions.addWidget(b_reset)
    v.addLayout(row_actions)
    win._route_fold_boxes = [sec_pick, sec_map, sec_stops]
    if sec_phone is not None:
        win._route_fold_boxes.append(sec_phone)
    return w
