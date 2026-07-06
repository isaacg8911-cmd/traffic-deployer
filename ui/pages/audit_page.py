"""Audit / export page."""
from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.simple_mode import COMPACT_UI


def build_audit_page(win) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    pad = 8 if COMPACT_UI else 16
    v.setContentsMargins(pad, pad, pad, pad)
    v.setSpacing(6 if COMPACT_UI else 10)
    win.lbl_shift_summary = QLabel("")
    win.lbl_shift_summary.setWordWrap(True)
    win.lbl_shift_summary.setObjectName("shiftSummary")
    v.addWidget(win.lbl_shift_summary)
    win.lbl_audit = QLabel("")
    win.lbl_audit.setWordWrap(True)
    win.lbl_audit.setObjectName("hint")
    v.addWidget(win.lbl_audit)
    row_sum = QHBoxLayout()
    b_refresh_sum = QPushButton("Refresh")
    b_refresh_sum.setObjectName("secondary")
    b_refresh_sum.clicked.connect(win._refresh_audit)
    row_sum.addWidget(b_refresh_sum)
    v.addLayout(row_sum)
    grid = QGridLayout()
    grid.setHorizontalSpacing(6)
    grid.setVerticalSpacing(6)
    b_xlsx = QPushButton("Handoff export")
    b_xlsx.setObjectName("primary")
    b_xlsx.clicked.connect(win._export_excel)
    grid.addWidget(b_xlsx, 0, 0, 1, 2)
    if COMPACT_UI:
        b_xlsx_quick = QPushButton("Quick handoff")
        b_xlsx_quick.clicked.connect(win._export_excel_quick)
        b_csv_quick = QPushButton("Quick CSV")
        b_csv_quick.setObjectName("secondary")
        b_csv_quick.clicked.connect(win._export_csv_quick)
        b_vol = QPushButton("Volume CSVs")
        b_vol.setObjectName("secondary")
        b_vol.clicked.connect(win._export_volume_csv_all)
        grid.addWidget(b_xlsx_quick, 1, 0)
        grid.addWidget(b_csv_quick, 1, 1)
        grid.addWidget(b_vol, 2, 0, 1, 2)
    else:
        b_xlsx_quick = QPushButton("Quick handoff → shift_handoff folder")
        b_xlsx_quick.clicked.connect(win._export_excel_quick)
        grid.addWidget(b_xlsx_quick, 1, 0, 1, 2)
        win.lbl_export_hint = QLabel("")
        win.lbl_export_hint.setWordWrap(True)
        win.lbl_export_hint.setStyleSheet("color:#6b7280;font-size:12px;")
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
