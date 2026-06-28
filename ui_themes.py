"""Field + desk themes for Traffic Deployer — distinctive, high-contrast Qt chrome."""

from __future__ import annotations

VALID_THEMES = ("sunny", "cloudy", "night")


def normalize_theme(raw: str | None) -> str:
    m = (raw or "").strip().lower()
    if m in VALID_THEMES:
        return m
    if m == "dark":
        return "night"
    if m == "light":
        return "sunny"
    return "sunny"


def qt_stylesheet(theme: str) -> str:
    t = normalize_theme(theme)
    if t == "night":
        return _NIGHT + _COMMON
    if t == "cloudy":
        return _CLOUDY + _COMMON
    return _SUNNY + _COMMON


_COMMON = """
QGroupBox#sectionCard {
    font-size: 12px; font-weight: 800; color: #475569;
    border: 1px solid #c5d0de; border-radius: 10px;
    margin-top: 12px; padding-top: 18px; background: #ffffff;
}
QGroupBox#sectionCardCompact {
    font-size: 11px; font-weight: 800; color: #64748b;
    border: 1px solid #d8e0ea; border-radius: 8px;
    margin-top: 8px; padding-top: 12px; background: #ffffff;
}
QGroupBox#sectionCard::title, QGroupBox#sectionCardCompact::title {
    subcontrol-origin: margin; left: 10px; padding: 0 4px;
}
#workflowStrip {
    background: #f0f4f9; border: 1px solid #c5d0de; border-radius: 10px;
}
#workflowStepDone {
    background: #0d5c4b; color: #fff; border-radius: 8px;
    padding: 6px 4px; font-size: 11px; font-weight: 800;
}
#workflowStepCurrent {
    background: #c45f14; color: #fff; border-radius: 8px;
    padding: 6px 4px; font-size: 11px; font-weight: 800;
}
#workflowStepPending {
    background: #e8edf3; color: #64748b; border-radius: 8px;
    padding: 6px 4px; font-size: 11px; font-weight: 700;
}
#workflowArrow { color: #94a3b8; font-size: 14px; font-weight: 700; }
#navRail {
    background: #0f2744; border-right: 1px solid #1a3a5c;
}
QPushButton#navBtn {
    background: transparent; color: #94b8d9; border: none;
    border-radius: 8px; padding: 8px 2px; font-size: 10px; font-weight: 700;
    min-height: 40px;
}
QPushButton#navBtn:hover { background: #1a3a5c; color: #fff; }
QPushButton#navBtn:checked {
    background: #c45f14; color: #fff; border: none;
}
#statCard {
    background: #ffffff; border: 1px solid #c5d0de; border-radius: 10px;
}
#statCardCompact {
    background: #ffffff; border: 1px solid #d8e0ea; border-radius: 8px;
}
#statTitle { font-size: 11px; font-weight: 700; color: #64748b; }
#statValue { font-size: 18px; font-weight: 800; color: #0f2744; }
#statCardCompact #statTitle { font-size: 10px; }
#statCardCompact #statValue { font-size: 15px; }
#tabContextLine {
    font-size: 13px; font-weight: 700; color: #334155;
    padding: 4px 0 2px 0; line-height: 1.35;
}
#mapOptions {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px;
}
#dayFilterBar { background: transparent; }
#dayFilterLabel {
    font-size: 11px; font-weight: 800; color: #94b8d9; letter-spacing: 0.4px;
}
QComboBox#dayFilterCombo {
    background: #1a3a5c; color: #f8fafc; border: 1px solid #3d5a80;
    border-radius: 6px; padding: 4px 8px; font-size: 12px; font-weight: 700;
    min-height: 24px;
}
QComboBox#dayFilterCombo:hover { background: #243f5c; }
QComboBox#dayFilterCombo::drop-down { border: none; width: 18px; }
QComboBox#dayFilterCombo QAbstractItemView {
    background: #ffffff; color: #0f2744; selection-background-color: #dbeafe;
}
QPushButton#secondary {
    background: #f1f5f9; border: 1px solid #94a3b8; font-weight: 600;
}
QPushButton#secondary:hover { background: #e2e8f0; }
#hint { color: #64748b; font-size: 12px; }
#counterPanel {
    border: 1px solid #7eb8e8; background: #f8fbff;
}
#counterPanel[counterConnected="true"] {
    border: 2px solid #22c55e; background: #ecfdf5;
}
#counterPanel[counterConnected="true"]::title {
    color: #15803d; font-weight: 800;
}
QLabel#counterConnectedPill {
    font-size: 11px; font-weight: 800; letter-spacing: 0.5px;
    color: #15803d; background: #dcfce7; border: 1px solid #86efac;
    border-radius: 6px; padding: 4px 10px;
}
QLabel#counterConnectedPill[visible="false"] { max-height: 0; padding: 0; border: none; }
QLabel#counterData {
    font-size: 12px; font-weight: 600; color: #475569;
}
QLabel#counterData[counterEmpty="true"] { color: #15803d; }
QLabel#counterStatus {
    border-radius: 8px; padding: 10px 12px; font-weight: 600; font-size: 13px;
    background: #f1f5f9; color: #334155; border: 1px solid #cbd5e1;
}
QLabel#counterStatusCompact {
    border-radius: 6px; padding: 6px 8px; font-weight: 600; font-size: 12px;
    background: #f1f5f9; color: #334155; border: 1px solid #cbd5e1;
}
QLabel#counterStatus[statusLevel="ok"],
QLabel#counterStatusCompact[statusLevel="ok"] {
    background: #ecfdf5; color: #065f46; border: 1px solid #6ee7b7;
}
QLabel#counterStatus[statusLevel="warn"] {
    background: #fffbeb; color: #92400e; border: 1px solid #fcd34d;
}
QLabel#counterStatus[statusLevel="fail"] {
    background: #fef2f2; color: #991b1b; border: 1px solid #fca5a5;
}
QLabel#counterStatus[statusLevel="busy"] {
    background: #eff6ff; color: #1e40af; border: 1px solid #93c5fd;
}
QLabel#counterVoltCheck,
QLabel#counterVoltCheckCompact {
    border-radius: 8px; padding: 8px 10px; font-weight: 700; font-size: 12px;
    background: #f8fafc; color: #475569; border: 1px solid #cbd5e1;
}
QLabel#counterVoltCheckCompact { padding: 6px 8px; font-size: 11px; }
QLabel#counterVoltCheck[statusLevel="ok"],
QLabel#counterVoltCheckCompact[statusLevel="ok"] {
    background: #ecfdf5; color: #065f46; border: 1px solid #6ee7b7;
}
QLabel#counterVoltCheck[statusLevel="warn"],
QLabel#counterVoltCheckCompact[statusLevel="warn"] {
    background: #fffbeb; color: #92400e; border: 1px solid #fcd34d;
}
QLabel#counterVoltCheck[statusLevel="fail"],
QLabel#counterVoltCheckCompact[statusLevel="fail"] {
    background: #fef2f2; color: #991b1b; border: 1px solid #fca5a5;
}
#counterInventoryPanel {
    border: 1px solid #c5d0de; background: #fbfdff;
}
QLabel#shiftSummary {
    font-size: 13px; font-weight: 700; color: #0f2744;
    background: #ffffff; border: 1px solid #c5d0de; border-radius: 10px;
    padding: 12px 14px;
}
#pickupCounterCard {
    background: #f8fbff; border: 1px solid #c5d0de; border-radius: 10px;
    padding: 4px;
}
QScrollBar:vertical {
    background: #f1f5f9; width: 10px; margin: 2px; border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #94a3b8; min-height: 24px; border-radius: 5px;
}
QScrollBar::handle:vertical:hover { background: #64748b; }
"""

# Default desk look — navy + amber (traffic-deployer identity).
_SUNNY = """
* { font-family: 'Segoe UI', system-ui, sans-serif; }
QMainWindow, QWidget { background: #eef2f7; color: #0f2744; font-size: 14px; }
#topbar {
    background: #0f2744; border-bottom: none; min-height: 48px;
}
#brand { font-size: 15px; font-weight: 800; color: #f8fafc; letter-spacing: 0.3px; }
#brandSub { font-size: 11px; font-weight: 600; color: #94b8d9; }
QPushButton#aboutBtn {
    background: transparent; color: #94b8d9; border: 1px solid #3d5a80;
    padding: 6px 12px; font-weight: 600;
}
QPushButton#aboutBtn:hover { background: #1a3a5c; color: #fff; }
#modePill {
    font-size: 11px; font-weight: 800; letter-spacing: 0.6px;
    padding: 6px 10px; border-radius: 6px; min-width: 64px;
}
#modePill[mode="online"] { background: #0d5c4b; color: #ecfdf5; }
#modePill[mode="offline"] { background: #c45f14; color: #fff; }
QPushButton#modeBtnOnline, QPushButton#modeBtnOffline {
    padding: 6px 12px; font-size: 12px; font-weight: 700;
    background: #1a3a5c; color: #cbd5e1; border: 1px solid #3d5a80;
}
QPushButton#modeBtnOnline:hover, QPushButton#modeBtnOffline:hover {
    background: #243f5c; color: #fff;
}
QPushButton#modeBtnOnline:checked {
    background: #0d5c4b; color: #fff; border: none;
}
QPushButton#modeBtnOffline:checked {
    background: #c45f14; color: #fff; border: none;
}
#sidepanel {
    background: #f8fafc; border-right: 2px solid #c5d0de;
}
#pagesColumn { background: #f8fafc; }
#mapFrame { background: #e8edf3; border-left: 2px solid #94a3b8; }
QSplitter#mainSplit::handle {
    background: #c5d0de; width: 3px;
}
QSplitter#mainSplit::handle:hover { background: #c45f14; }
#pageScroll { background: #f8fafc; }
#installHeader {
    background: #ffffff; border: 1px solid #c5d0de; border-radius: 12px;
}
#installHeaderCompact {
    background: #ffffff; border: 1px solid #d8e0ea; border-radius: 8px;
}
#installTitle { font-size: 18px; font-weight: 800; color: #0f2744; }
#installHeaderCompact #installTitle { font-size: 15px; }
#installSub { font-size: 13px; font-weight: 600; color: #475569; }
#installHeaderCompact #installSub { font-size: 12px; font-weight: 600; }
#installWarn { color: #b42318; font-weight: 700; font-size: 12px; }
#pickupReminder {
    font-size: 12px; font-weight: 800; color: #9a3412;
    background: #fff7ed; border: 1px solid #fdba74; border-radius: 8px;
    padding: 10px 12px;
}
#installChecklist {
    font-size: 12px; font-weight: 700; color: #475569;
    background: #f8fafc; border: 1px solid #c5d0de; border-radius: 8px;
    padding: 10px 12px;
}
#installChecklist[allReady="true"] {
    background: #ecfdf5; border: 1px solid #6ee7b7; color: #065f46;
}
#installCompass { font-weight: 700; font-size: 14px; color: #0f2744; }
QLabel[role="h"] {
    font-size: 11px; font-weight: 800; color: #64748b;
    letter-spacing: 0.8px; padding-top: 4px;
}
QLabel[role="title"] { font-size: 17px; font-weight: 800; color: #0f2744; }
QPushButton {
    background: #ffffff; border: 1px solid #94a3b8; border-radius: 8px;
    padding: 9px 12px; font-weight: 600; color: #0f2744;
}
QPushButton:hover { background: #f1f5f9; border-color: #64748b; }
QPushButton:pressed { background: #e2e8f0; }
QPushButton:disabled { background: #e8edf3; color: #94a3b8; }
QPushButton#primary {
    background: #c45f14; color: #fff; border: none;
    font-weight: 800; padding: 12px; font-size: 14px;
}
QPushButton#primary:hover { background: #a04f10; }
QPushButton#go {
    background: #0d5c4b; color: #fff; border: none;
    font-weight: 800; padding: 14px; font-size: 15px;
}
QPushButton#go:hover { background: #0a4a3d; }
QPushButton#stop {
    background: #b42318; color: #fff; border: none;
    font-weight: 800; padding: 14px; font-size: 15px;
}
QPushButton#stop:hover { background: #912018; }
QPushButton#fieldPrimary {
    background: #0d5c4b; color: #fff; border: none;
    font-weight: 800; padding: 16px; font-size: 16px; min-height: 24px;
}
QPushButton#fieldSkip {
    background: #64748b; color: #fff; border: none;
    font-weight: 800; padding: 16px; font-size: 16px; min-height: 24px;
}
QPushButton#themeBtn {
    padding: 6px 10px; font-size: 11px; min-width: 52px;
    background: #1a3a5c; color: #cbd5e1; border: 1px solid #3d5a80;
}
QPushButton#themeBtn:checked { background: #c45f14; color: #fff; border: none; }
QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    background: #ffffff; border: 1px solid #94a3b8; border-radius: 8px;
    padding: 8px; color: #0f2744; font-size: 14px;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 2px solid #c45f14; }
QListWidget {
    background: #ffffff; border: 1px solid #c5d0de; border-radius: 8px;
}
QListWidget::item { padding: 8px; border-bottom: 1px solid #eef2f7; }
QListWidget::item:selected { background: #dbeafe; color: #0f2744; font-weight: 700; }
QStatusBar {
    background: #0f2744; color: #e2e8f0; border-top: none; font-weight: 600; padding: 4px;
}
QStatusBar QLabel { color: #e2e8f0; }
QScrollArea { border: none; background: transparent; }
QCheckBox { font-weight: 600; spacing: 8px; }
#placeholder { background: linear-gradient(180deg, #e8edf3 0%, #dbe4ef 100%); }
#phTitle { font-size: 28px; font-weight: 800; color: #0f2744; }
#phSub { font-size: 14px; font-weight: 700; color: #c45f14; }
#phText { font-size: 14px; color: #475569; font-weight: 500; line-height: 1.5; }
#phStep {
    background: #ffffff; border: 1px solid #c5d0de; border-radius: 10px;
    padding: 14px 18px; font-size: 14px; color: #334155; font-weight: 600;
}
#driveBanner {
    background: #e8f4fc; border: 1px solid #7eb8e8; border-radius: 8px;
    padding: 10px; font-weight: 700; font-size: 13px; color: #0c4a6e;
}
"""

_CLOUDY = """
* { font-family: 'Segoe UI', system-ui, sans-serif; }
QMainWindow, QWidget { background: #e2e8f0; color: #0c1929; font-size: 14px; }
#topbar { background: #1e3a5f; border-bottom: none; }
#brand { font-size: 15px; font-weight: 800; color: #f8fafc; }
#brandSub { font-size: 11px; color: #93c5fd; }
QPushButton#aboutBtn { background: transparent; color: #93c5fd; border: 1px solid #3b5998; }
#sidepanel { background: #f1f5f9; border-right: 1px solid #94a3b8; }
QPushButton#primary { background: #1d4ed8; color: #fff; border: none; font-weight: 800; }
QPushButton#go { background: #047857; color: #fff; border: none; font-weight: 800; padding: 14px; }
QPushButton#stop { background: #dc2626; color: #fff; border: none; font-weight: 800; padding: 14px; }
QPushButton#fieldPrimary { background: #047857; color: #fff; border: none; font-weight: 800; padding: 16px; }
QPushButton#fieldSkip { background: #64748b; color: #fff; border: none; font-weight: 800; padding: 16px; }
QStatusBar { background: #1e3a5f; color: #e2e8f0; }
QStatusBar QLabel { color: #e2e8f0; }
#placeholder { background: #cbd5e1; }
#phTitle { font-size: 28px; font-weight: 800; color: #1e3a5f; }
#phSub { color: #1d4ed8; font-weight: 700; }
"""

_NIGHT = """
* { font-family: 'Segoe UI', system-ui, sans-serif; }
QMainWindow, QWidget { background: #121820; color: #e8eaed; font-size: 14px; }
#topbar { background: #0a1628; border-bottom: 1px solid #2a3a50; }
#brand { font-size: 15px; font-weight: 800; color: #e8eaed; }
#brandSub { font-size: 11px; color: #7eb8ff; }
#sidepanel { background: #1a2230; border-right: 1px solid #2a3a50; }
QGroupBox#sectionCard { background: #222b3a; border-color: #3d4f66; color: #cbd5e1; }
#statCard { background: #222b3a; border-color: #3d4f66; }
#statValue { color: #e8eaed; }
QPushButton#primary { background: #3b82f6; color: #fff; border: none; }
QPushButton#go { background: #16a34a; color: #fff; border: none; font-weight: 800; padding: 14px; }
QPushButton#stop { background: #dc2626; color: #fff; border: none; font-weight: 800; padding: 14px; }
QStatusBar { background: #0a1628; color: #cbd5e1; }
#placeholder { background: #0f141c; }
#phTitle { color: #7eb8ff; }
"""
