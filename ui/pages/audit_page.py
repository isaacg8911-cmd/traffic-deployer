"""Audit / export page."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


def build_audit_page(win) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(16, 14, 16, 14)
    v.addWidget(win._h("END OF DAY AUDIT"))
    win.lbl_shift_summary = QLabel("")
    win.lbl_shift_summary.setWordWrap(True)
    win.lbl_shift_summary.setStyleSheet("font-weight:700;font-size:13px;color:#0f2744;")
    v.addWidget(win.lbl_shift_summary)
    win.lbl_audit = QLabel("")
    win.lbl_audit.setWordWrap(True)
    v.addWidget(win.lbl_audit)
    row_sum = QHBoxLayout()
    b_refresh_sum = QPushButton("Refresh shift summary")
    b_refresh_sum.setObjectName("secondary")
    b_refresh_sum.clicked.connect(win._refresh_audit)
    row_sum.addWidget(b_refresh_sum)
    v.addLayout(row_sum)
    b_xlsx = QPushButton("Export Excel (.xlsx)")
    b_xlsx.setObjectName("primary")
    b_xlsx.clicked.connect(win._export_excel)
    v.addWidget(b_xlsx)
    b_xlsx_quick = QPushButton("Quick export Excel → default folder")
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
    v.addStretch(1)
    return w
