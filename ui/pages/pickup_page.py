"""Pickup page."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.simple_mode import COMPACT_UI


def build_pickup_page(win) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    pad = 8 if COMPACT_UI else 16
    v.setContentsMargins(pad, pad, pad, pad)
    v.setSpacing(6 if COMPACT_UI else 10)

    win.lbl_download_reminder = QLabel("")
    win.lbl_download_reminder.setObjectName("pickupReminder")
    win.lbl_download_reminder.setWordWrap(True)
    win.lbl_download_reminder.hide()
    v.addWidget(win.lbl_download_reminder)
    win.lbl_pickup_prog = QLabel("")
    win.lbl_pickup_prog.setObjectName("tabContextLine")
    v.addWidget(win.lbl_pickup_prog)
    win.chk_pickup_pending = QCheckBox("Not picked up only")
    win.chk_pickup_pending.setChecked(True)
    win.chk_pickup_pending.stateChanged.connect(win._refresh_pickup)
    v.addWidget(win.chk_pickup_pending)
    win.list_pickup = QListWidget()
    win.list_pickup.setMinimumHeight(100 if COMPACT_UI else 140)
    win.list_pickup.itemClicked.connect(win._pickup_item_clicked)
    v.addWidget(win.list_pickup, 1)
    win.lbl_pickup_cur = QLabel("")
    v.addWidget(win.lbl_pickup_cur)
    b_sec = QPushButton("SECURED")
    b_sec.setObjectName("primary")
    b_sec.clicked.connect(win._mark_pickup)
    v.addWidget(b_sec)
    win.btn_counter_download = QPushButton("Download counter data")
    win.btn_counter_download.setObjectName("primary")
    win.btn_counter_download.setEnabled(False)
    win.btn_counter_download.clicked.connect(win._counter_download_pickup)
    v.addWidget(win.btn_counter_download)
    win.btn_volume_csv = QPushButton("Export volume CSV (1029 format)")
    win.btn_volume_csv.setObjectName("secondary")
    win.btn_volume_csv.clicked.connect(win._export_volume_csv_pickup)
    v.addWidget(win.btn_volume_csv)
    if COMPACT_UI:
        b_export = QPushButton("Export Excel")
        b_export.setObjectName("secondary")
        b_export.clicked.connect(win._export_excel_quick)
        v.addWidget(b_export)
    win.lbl_counter_download = QLabel("")
    win.lbl_counter_download.setObjectName("hint")
    win.lbl_counter_download.setWordWrap(True)
    v.addWidget(win.lbl_counter_download)
    row_pick = QHBoxLayout()
    win.btn_undo_pickup = QPushButton("Undo")
    win.btn_undo_pickup.setEnabled(False)
    win.btn_undo_pickup.clicked.connect(win._undo_last_action)
    b_pick_prev = QPushButton("← Prev")
    b_pick_prev.clicked.connect(lambda: win._nav_pickup(-1))
    b_pick_next = QPushButton("Next →")
    b_pick_next.clicked.connect(lambda: win._nav_pickup(1))
    row_pick.addWidget(win.btn_undo_pickup)
    row_pick.addWidget(b_pick_prev, 1)
    row_pick.addWidget(b_pick_next, 1)
    v.addLayout(row_pick)
    return w
