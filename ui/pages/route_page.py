"""Route tab — drive, map, stop list."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.simple_mode import SIMPLE_MODE
from ui.widgets import button_row, more_panel, numbered_section, page_column, page_with_footer, section_group


def build_route_page(win) -> QWidget:
    if SIMPLE_MODE:
        w, v, foot, _footer = page_with_footer()
    else:
        w, v = page_column()
        foot = v

    win.lbl_route_summary = QLabel("")
    win.lbl_route_summary.setObjectName("tabContextLine")
    win.lbl_route_summary.setWordWrap(True)
    v.addWidget(win.lbl_route_summary)

    win.lbl_route_stats = QLabel("")
    win.lbl_route_stats.hide()
    win.lbl_field_strip = QLabel("")
    win.lbl_field_strip.hide()

    win.lbl_drive_banner = QLabel("")
    win.lbl_drive_banner.setWordWrap(True)
    win.lbl_drive_banner.setObjectName("driveBanner")
    win.lbl_drive_banner.hide()
    v.addWidget(win.lbl_drive_banner)

    win.btn_start = QPushButton("Follow GPS")
    win.btn_start.setObjectName("go")
    win.btn_start.setToolTip("GPS marker stays live; map recenters only when you tap Follow.")
    win.btn_start.clicked.connect(win._toggle_drive)
    if SIMPLE_MODE:
        win.btn_start.setMinimumHeight(44)
        foot.addWidget(win.btn_start)
        win.btn_pick_on_map = QPushButton("Pick on map")
        win.btn_pick_on_map.setObjectName("secondary")
        win.btn_pick_on_map.setToolTip(
            "Choose stop order by tapping blue (begin) and red (end) dots on the map.")
        win.btn_pick_on_map.clicked.connect(win._start_pick_route_from_route_tab)
        win.btn_merge_days = QPushButton("Merge days")
        win.btn_merge_days.setObjectName("secondary")
        win.btn_merge_days.setToolTip(
            "After Day 1 and Day 2 exist: one new best driving order from all sites, by location.")
        win.btn_merge_days.clicked.connect(win._offer_merge_days)
    else:
        sec_drive = section_group("Navigate", v)
        sec_drive.addWidget(win.btn_start)

    sec_pick_lay = section_group("Plan route", v)
    sec_pick = sec_pick_lay.parentWidget()
    win.lbl_pick_status = QLabel("Pick stop order on the map or in the popup.")
    win.lbl_pick_status.setObjectName("pickStatus")
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
    win.pick_side_row = QWidget()
    row_side = QHBoxLayout(win.pick_side_row)
    row_side.setContentsMargins(0, 0, 0, 0)
    win.lbl_pick_side = QLabel("Drive-to:")
    win.lbl_pick_side.setMinimumWidth(52)
    win.btn_pick_side_begin = QPushButton("Begin")
    win.btn_pick_side_begin.setObjectName("secondary")
    win.btn_pick_side_begin.setCheckable(True)
    win.btn_pick_side_begin.setChecked(True)
    win.btn_pick_side_begin.setToolTip("Next stop from the list uses the blue (begin) end")
    win.btn_pick_side_end = QPushButton("End")
    win.btn_pick_side_end.setObjectName("secondary")
    win.btn_pick_side_end.setCheckable(True)
    win.btn_pick_side_end.setToolTip("Next stop from the list uses the red (end) end")
    win._pick_side_group = QButtonGroup(win.pick_side_row)
    win._pick_side_group.setExclusive(True)
    for btn in (win.btn_pick_side_begin, win.btn_pick_side_end):
        win._pick_side_group.addButton(btn)
    win.btn_pick_side_begin.clicked.connect(lambda: win._set_pick_side_mode("begin"))
    win.btn_pick_side_end.clicked.connect(lambda: win._set_pick_side_mode("end"))
    row_side.addWidget(win.lbl_pick_side)
    row_side.addWidget(win.btn_pick_side_begin)
    row_side.addWidget(win.btn_pick_side_end)
    row_side.addStretch(1)
    win.pick_side_row.hide()
    sec_pick_lay.addWidget(win.pick_side_row)
    win.btn_pick_clear = QPushButton("Clear")
    win.btn_pick_clear.setObjectName("secondary")
    win.btn_pick_clear.clicked.connect(win._route_pick_clear)
    win.btn_pick_apply = QPushButton("Apply route")
    win.btn_pick_apply.setObjectName("primary")
    win.btn_pick_apply.setMinimumHeight(44)
    win.btn_pick_apply.clicked.connect(win._route_pick_apply)
    button_row(sec_pick_lay, win.btn_pick_clear, win.btn_pick_apply)
    win.btn_pick_order_win = QPushButton("Route order window")
    win.btn_pick_order_win.setObjectName("secondary")
    win.btn_pick_order_win.clicked.connect(win._show_route_pick_dialog)
    sec_pick_lay.addWidget(win.btn_pick_order_win)
    win.sec_pick = sec_pick
    if SIMPLE_MODE and sec_pick is not None:
        sec_pick.hide()

    win.chk_show_segments = QCheckBox("Site lines")
    win.chk_show_segments.setChecked(False)
    win.chk_show_segments.hide()
    win.chk_show_segments.stateChanged.connect(lambda: win._push_state())
    b_fit = QPushButton("Zoom all")
    b_fit.setObjectName("secondary")
    b_fit.clicked.connect(lambda: win._push_state(fit=True))

    if SIMPLE_MODE:
        sec_stops_lay, _ = numbered_section(1, "Stops", v)
        sec_map = None
        sec_stops = None
    else:
        sec_map_lay = section_group("Map", v)
        sec_map = sec_map_lay.parentWidget()
        button_row(sec_map_lay, win.chk_show_segments, b_fit)
        sec_stops_lay = section_group("Stops", v, stretch=1)
        sec_stops = sec_stops_lay.parentWidget()
    win.list_route = QListWidget()
    win.list_route.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    win.list_route.itemClicked.connect(win._route_item_clicked)
    sec_stops_lay.addWidget(win.list_route, 1)

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
    b_reopt = QPushButton("Pick order…")
    b_reopt.setObjectName("secondary")
    b_reopt.clicked.connect(win._reoptimize)
    b_reset = QPushButton("Clear shift…")
    b_reset.setObjectName("secondary")
    b_reset.clicked.connect(win._reset_route)
    b_install_links = QPushButton("HTML route")
    b_install_links.setObjectName("secondary")
    b_install_links.setToolTip(
        "Save HTML install lists: both days merged, each day separate, or this map only.",
    )
    b_install_links.clicked.connect(win._save_install_nav_links)
    b_pickup_links = QPushButton("HTML pickup")
    b_pickup_links.setObjectName("secondary")
    b_pickup_links.setToolTip("Save HTML with one link per installed site, oldest first.")
    b_pickup_links.clicked.connect(win._save_pickup_nav_links)

    if SIMPLE_MODE:
        _more_btn, more_lay = more_panel(v)
        button_row(more_lay, win.btn_pick_on_map, win.btn_merge_days)
        button_row(more_lay, b_fit)
        more_lay.addWidget(win.chk_show_segments)
        button_row(more_lay, b_up, b_dn, b_retrace)
        button_row(more_lay, b_reopt, b_reset)
        button_row(more_lay, b_install_links, b_pickup_links)
        sec_phone = None
        win._route_fold_boxes = []
    else:
        button_row(sec_stops_lay, b_up, b_dn, b_retrace)
        button_row(sec_stops_lay, b_reopt, b_reset)
        sec_phone_lay = section_group("Phone links", v)
        sec_phone = sec_phone_lay.parentWidget()
        button_row(sec_phone_lay, b_install_links, b_pickup_links)
        win._route_fold_boxes = [sec_pick, sec_map, sec_stops]
        if sec_phone is not None:
            win._route_fold_boxes.append(sec_phone)

    win.lbl_stat_stops = win.lbl_stat_miles = win.lbl_stat_kind = None
    return w
