"""Pickup page — mark sites secured (counter download is TrafficViewer)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.simple_mode import COMPACT_UI
from ui.spacing import apply_row
from ui.widgets import more_panel, page_column, page_with_footer


def build_pickup_page(win) -> QWidget:
    if COMPACT_UI:
        w, v, foot, _footer = page_with_footer()
    else:
        w, v = page_column()
        foot = v

    win.lbl_pickup_prog = QLabel("")
    win.lbl_pickup_prog.setObjectName("tabContextLine")
    v.addWidget(win.lbl_pickup_prog)
    win.chk_pickup_pending = QCheckBox("Not picked up only")
    win.chk_pickup_pending.setChecked(True)
    win.chk_pickup_pending.stateChanged.connect(win._refresh_pickup)
    v.addWidget(win.chk_pickup_pending)
    win.list_pickup = QListWidget()
    win.list_pickup.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    win.list_pickup.itemClicked.connect(win._pickup_item_clicked)
    v.addWidget(win.list_pickup, 1)
    win.lbl_pickup_cur = QLabel("")
    win.lbl_pickup_cur.setObjectName("tabContextLine")
    v.addWidget(win.lbl_pickup_cur)
    b_sec = QPushButton("SECURED")
    b_sec.setObjectName("primary")
    b_sec.setMinimumHeight(44)
    b_sec.clicked.connect(win._mark_pickup)
    if COMPACT_UI:
        _more_btn, more_lay = more_panel(v)
        b_export = QPushButton("Export Excel")
        b_export.setObjectName("secondary")
        b_export.clicked.connect(win._export_excel_quick)
        more_lay.addWidget(b_export)
    row_pick = QHBoxLayout()
    apply_row(row_pick)
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
    foot.addLayout(row_pick)
    foot.addWidget(b_sec)
    return w
