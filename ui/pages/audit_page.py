"""Audit / export page."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QWidget,
)

from ui.simple_mode import COMPACT_UI
from ui.spacing import apply_grid
from ui.widgets import button_row, more_panel, page_column, page_with_footer


def build_audit_page(win) -> QWidget:
    if COMPACT_UI:
        w, v, foot, _footer = page_with_footer()
    else:
        w, v = page_column()
        foot = v

    win.lbl_shift_summary = QLabel("")
    win.lbl_shift_summary.setWordWrap(True)
    win.lbl_shift_summary.setObjectName("shiftSummary")
    v.addWidget(win.lbl_shift_summary)

    win.lbl_audit = QLabel("")
    win.lbl_audit.setWordWrap(True)
    win.lbl_audit.setObjectName("hint")
    v.addWidget(win.lbl_audit)

    lbl_sheet = QLabel("Live shift data — same columns as handoff Excel")
    lbl_sheet.setObjectName("hint")
    v.addWidget(lbl_sheet)
    win.table_audit_sheet = QTableWidget(0, 10)
    win.table_audit_sheet.setHorizontalHeaderLabels([
        "Seq", "Site", "Street", "Serial", "Dir", "Lanes",
        "Installed", "Skipped", "Pickup", "GPS",
    ])
    win.table_audit_sheet.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents)
    win.table_audit_sheet.horizontalHeader().setStretchLastSection(True)
    win.table_audit_sheet.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    win.table_audit_sheet.setSelectionBehavior(
        QTableWidget.SelectionBehavior.SelectRows)
    win.table_audit_sheet.setAlternatingRowColors(True)
    win.table_audit_sheet.setMinimumHeight(180 if COMPACT_UI else 220)
    v.addWidget(win.table_audit_sheet, 1)

    b_xlsx = QPushButton("Handoff export")
    b_xlsx.setObjectName("primary")
    b_xlsx.setMinimumHeight(44)
    b_xlsx.clicked.connect(win._export_excel)

    if COMPACT_UI:
        _more_btn, more_lay = more_panel(v)
        b_refresh_sum = QPushButton("Refresh")
        b_refresh_sum.setObjectName("secondary")
        b_refresh_sum.clicked.connect(win._refresh_audit)
        b_xlsx_quick = QPushButton("Quick handoff")
        b_xlsx_quick.clicked.connect(win._export_excel_quick)
        b_csv_quick = QPushButton("Quick CSV")
        b_csv_quick.setObjectName("secondary")
        b_csv_quick.clicked.connect(win._export_csv_quick)
        button_row(more_lay, b_refresh_sum)
        button_row(more_lay, b_xlsx_quick, b_csv_quick)
        foot.addWidget(b_xlsx)
    else:
        b_refresh_sum = QPushButton("Refresh")
        b_refresh_sum.setObjectName("secondary")
        b_refresh_sum.clicked.connect(win._refresh_audit)
        button_row(v, b_refresh_sum)
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
        v.addLayout(grid)

    return w
