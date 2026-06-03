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


def build_pickup_page(win) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(16, 14, 16, 14)
    v.addWidget(win._h("PICK-UP"))
    win.lbl_pickup_prog = QLabel("")
    v.addWidget(win.lbl_pickup_prog)
    win.chk_pickup_pending = QCheckBox("Show only not picked up yet")
    win.chk_pickup_pending.setChecked(True)
    win.chk_pickup_pending.stateChanged.connect(win._refresh_pickup)
    v.addWidget(win.chk_pickup_pending)
    win.list_pickup = QListWidget()
    win.list_pickup.itemClicked.connect(win._pickup_item_clicked)
    v.addWidget(win.list_pickup, 1)
    win.lbl_pickup_cur = QLabel("")
    v.addWidget(win.lbl_pickup_cur)
    b_sec = QPushButton("SECURED (picked up)")
    b_sec.setObjectName("primary")
    b_sec.clicked.connect(win._mark_pickup)
    v.addWidget(b_sec)
    win.btn_counter_download = QPushButton("Download counter data")
    win.btn_counter_download.setObjectName("secondary")
    win.btn_counter_download.clicked.connect(win._counter_download_pickup)
    v.addWidget(win.btn_counter_download)
    win.lbl_counter_download = QLabel("")
    win.lbl_counter_download.setObjectName("hint")
    win.lbl_counter_download.setWordWrap(True)
    v.addWidget(win.lbl_counter_download)
    win.btn_undo_pickup = QPushButton("Undo last action  (Ctrl+Z)")
    win.btn_undo_pickup.setEnabled(False)
    win.btn_undo_pickup.clicked.connect(win._undo_last_action)
    v.addWidget(win.btn_undo_pickup)
    row_pick = QHBoxLayout()
    b_pick_prev = QPushButton("< Prev")
    b_pick_prev.clicked.connect(lambda: win._nav_pickup(-1))
    b_pick_next = QPushButton("Next >")
    b_pick_next.clicked.connect(lambda: win._nav_pickup(1))
    row_pick.addWidget(b_pick_prev)
    row_pick.addWidget(b_pick_next)
    v.addLayout(row_pick)
    return w
