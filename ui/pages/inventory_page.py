"""Fleet counter inventory — desk tab; UI refreshes only while this page is open."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.counter_ui import apply_volt_check
from ui.simple_mode import COMPACT_UI
from ui.widgets import section_group


def build_inventory_page(win) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    pad = 8 if COMPACT_UI else 14
    v.setContentsMargins(pad, pad, pad, pad)
    v.setSpacing(6 if COMPACT_UI else 10)

    sec_inv = section_group("Counter inventory", v, object_name="counterInventoryPanel")
    win.lbl_inventory_summary = QLabel(
        "Serials update in the background when you connect on Install/Pickup.")
    win.lbl_inventory_summary.setObjectName("hint")
    win.lbl_inventory_summary.setWordWrap(True)
    sec_inv.addWidget(win.lbl_inventory_summary)
    win.lbl_inventory_live = QLabel("Last USB read shows here.")
    win.lbl_inventory_live.setObjectName("counterVoltCheck")
    win.lbl_inventory_live.setWordWrap(True)
    apply_volt_check(win.lbl_inventory_live, None)
    sec_inv.addWidget(win.lbl_inventory_live)

    row_refresh = QHBoxLayout()
    b_refresh = QPushButton("Refresh fleet list")
    b_refresh.setObjectName("secondary")
    b_refresh.clicked.connect(win._refresh_counter_inventory)
    row_refresh.addWidget(b_refresh)
    row_refresh.addStretch(1)
    sec_inv.addLayout(row_refresh)

    win.table_counter_inventory = QTableWidget(0, 6)
    win.table_counter_inventory.setHorizontalHeaderLabels(
        ["Serial", "Battery", "Unit ID", "Status", "Data", "Last check"])
    win.table_counter_inventory.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.Stretch)
    win.table_counter_inventory.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    win.table_counter_inventory.setSelectionBehavior(
        QTableWidget.SelectionBehavior.SelectRows)
    win.table_counter_inventory.setAlternatingRowColors(True)
    sec_inv.addWidget(win.table_counter_inventory, 1)

    hint = QLabel(
        "Open this tab when you want the fleet table. "
        "Install and Pickup stay fast — inventory still records in the background.")
    hint.setObjectName("hint")
    hint.setWordWrap(True)
    v.addWidget(hint)
    return w
