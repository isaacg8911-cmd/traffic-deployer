"""Audit / export page."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

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
    v.addWidget(win.lbl_audit)
    row_sum = QHBoxLayout()
    b_refresh_sum = QPushButton("Refresh")
    b_refresh_sum.setObjectName("secondary")
    b_refresh_sum.clicked.connect(win._refresh_audit)
    row_sum.addWidget(b_refresh_sum)
    v.addLayout(row_sum)
    b_xlsx = QPushButton("Export shift handoff (IG TFC + maps)")
    b_xlsx.setObjectName("primary")
    b_xlsx.clicked.connect(win._export_excel)
    v.addWidget(b_xlsx)
    if COMPACT_UI:
        b_xlsx_quick = QPushButton("Quick handoff → shift_handoff folder")
        b_xlsx_quick.clicked.connect(win._export_excel_quick)
        v.addWidget(b_xlsx_quick)
        b_csv_quick = QPushButton("Quick CSV → default folder")
        b_csv_quick.setObjectName("secondary")
        b_csv_quick.clicked.connect(win._export_csv_quick)
        v.addWidget(b_csv_quick)
        b_vol = QPushButton("Export all volume CSVs (1029 format)")
        b_vol.setObjectName("secondary")
        b_vol.clicked.connect(win._export_volume_csv_all)
        v.addWidget(b_vol)
    else:
        b_xlsx_quick = QPushButton("Quick handoff → shift_handoff folder")
        b_xlsx_quick.clicked.connect(win._export_excel_quick)
        v.addWidget(b_xlsx_quick)
        win.lbl_export_hint = QLabel("")
        win.lbl_export_hint.setWordWrap(True)
        win.lbl_export_hint.setStyleSheet("color:#6b7280;font-size:12px;")
        v.addWidget(win.lbl_export_hint)
        win._refresh_export_hint()
        b_csv = QPushButton("Export CSV")
        b_csv.clicked.connect(win._export_csv)
        v.addWidget(b_csv)
        b_csv_quick = QPushButton("Quick export CSV → default folder")
        b_csv_quick.clicked.connect(win._export_csv_quick)
        v.addWidget(b_csv_quick)
        b_vol = QPushButton("Export all volume CSVs (1029 format)")
        b_vol.clicked.connect(win._export_volume_csv_all)
        v.addWidget(b_vol)
    return w
