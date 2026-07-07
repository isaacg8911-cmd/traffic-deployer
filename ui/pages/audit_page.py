"""Audit / export page."""
from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.simple_mode import COMPACT_UI
from ui.spacing import apply_grid
from ui.widgets import button_row, page_column


def build_audit_page(win) -> QWidget:
    w, v = page_column()
    win.lbl_shift_summary = QLabel("")
    win.lbl_shift_summary.setWordWrap(True)
    win.lbl_shift_summary.setObjectName("shiftSummary")
    v.addWidget(win.lbl_shift_summary)
    win.lbl_audit = QLabel("")
    win.lbl_audit.setWordWrap(True)
    win.lbl_audit.setObjectName("hint")
    v.addWidget(win.lbl_audit)
    b_refresh_sum = QPushButton("Refresh")
    b_refresh_sum.setObjectName("secondary")
    b_refresh_sum.clicked.connect(win._refresh_audit)
    button_row(v, b_refresh_sum)

    b_xlsx = QPushButton("Handoff export")
    b_xlsx.setObjectName("primary")
    b_xlsx.clicked.connect(win._export_excel)
    if COMPACT_UI:
        b_xlsx_quick = QPushButton("Quick handoff")
        b_xlsx_quick.clicked.connect(win._export_excel_quick)
        b_csv_quick = QPushButton("Quick CSV")
        b_csv_quick.setObjectName("secondary")
        b_csv_quick.clicked.connect(win._export_csv_quick)
        b_vol = QPushButton("Volume CSVs")
        b_vol.setObjectName("secondary")
        b_vol.clicked.connect(win._export_volume_csv_all)
        button_row(v, b_xlsx, b_xlsx_quick)
        button_row(v, b_csv_quick, b_vol)
    else:
        grid = QGridLayout()
        apply_grid(grid)
        grid.addWidget(b_xlsx, 0, 0, 1, 2)
        b_xlsx_quick = QPushButton("Quick handoff → shift_handoff folder")
        b_xlsx_quick.clicked.connect(win._export_excel_quick)
        grid.addWidget(b_xlsx_quick, 1, 0, 1, 2)
        win.lbl_export_hint = QLabel("")
        win.lbl_export_hint.setWordWrap(True)
        win.lbl_export_hint.setObjectName("hint")
        v.addWidget(win.lbl_export_hint)
        win._refresh_export_hint()
        b_csv = QPushButton("Export CSV")
        b_csv.clicked.connect(win._export_csv)
        grid.addWidget(b_csv, 2, 0)
        b_csv_quick = QPushButton("Quick CSV")
        b_csv_quick.clicked.connect(win._export_csv_quick)
        grid.addWidget(b_csv_quick, 2, 1)
        b_vol = QPushButton("Volume CSVs")
        b_vol.clicked.connect(win._export_volume_csv_all)
        grid.addWidget(b_vol, 3, 0, 1, 2)
        v.addLayout(grid)
    return w
