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
QGroupBox#sectionCard, QGroupBox#sectionCardCompact {
    font-size: 12px; font-weight: 800; color: #475569;
    border: 1px solid #c5d0de; border-radius: 10px;
    margin-top: 10px; padding-top: 16px; background: #ffffff;
}
QGroupBox#sectionFlat {
    font-size: 12px; font-weight: 700; color: #334155;
    border: none; border-top: 1px solid #cbd5e1;
    border-radius: 0; margin-top: 4px; padding-top: 8px;
    background: transparent;
}
QGroupBox#sectionFlat::title {
    subcontrol-origin: margin; left: 0; padding: 0 4px 0 0;
    color: #334155;
}
#sectionHeading, QLabel#stepHeader {
    font-size: 12px; font-weight: 800; color: #0f2744;
    padding: 6px 0 2px 0;
}
QLabel#stepHeaderDone { color: #15803d; }
QLabel#stepHeaderCurrent { color: #c45f14; }
QLabel#stepHeaderPending { color: #64748b; font-weight: 700; }
QGroupBox#sectionCardCompact {
    border-color: #94a3b8; border-radius: 8px;
    margin-top: 8px; padding-top: 14px;
}
QGroupBox#sectionCard::title, QGroupBox#sectionCardCompact::title {
    subcontrol-origin: margin; left: 12px; padding: 0 6px;
    color: #334155;
}
#statCard, #statCardCompact {
    background: #ffffff; border: 1px solid #c5d0de; border-radius: 10px;
}
#statCardCompact { border-radius: 8px; }
#installHeader {
    background: #ffffff; border: 1px solid #c5d0de; border-radius: 12px;
}
#installHeaderCompact {
    background: transparent; border: none; border-radius: 0;
}
#tabContextLine {
    font-size: 13px; font-weight: 700; color: #0f2744;
    padding: 2px 0;
}
#tabContextLine[statusLevel="ok"] { color: #15803d; }
#tabContextLine[statusLevel="warn"] { color: #b45309; }
#tabContextLine[statusLevel="fail"] { color: #b91c1c; }
#pickStatus {
    font-size: 12px; font-weight: 600; color: #64748b; padding: 2px 0;
}
#pickStatus[active="true"] {
    font-size: 13px; font-weight: 700; color: #0d47a1; padding: 4px 0;
}
#hint[statusLevel="warn"] { color: #b45309; font-weight: 700; }
#hint[statusLevel="fail"] { color: #b91c1c; font-weight: 700; }
#offlineHint[statusLevel="field"] { color: #138a3e; font-weight: 700; }
#offlineHint[statusLevel="home"] { color: #475569; font-size: 12px; font-weight: 600; }
#installChecklist {
    font-size: 12px; font-weight: 600; color: #475569;
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 8px 10px;
}
#counterData { font-size: 12px; font-weight: 600; color: #334155; }
#pickupReminder {
    background: #fffbeb; border: 1px solid #fcd34d; border-radius: 8px;
    padding: 8px 10px; font-weight: 700; font-size: 12px; color: #92400e;
}
#counterConnectedPill {
    font-size: 11px; font-weight: 800; color: #065f46;
    background: #ecfdf5; border: 1px solid #6ee7b7; border-radius: 6px;
    padding: 4px 8px;
}
QGroupBox#counterPanel, QGroupBox#counterInventoryPanel {
    border: 1px solid #7eb8e8; background: #f8fbff;
}
QGroupBox#counterPanel::title, QGroupBox#counterInventoryPanel::title { color: #0c4a6e; }
QLabel#counterVoltCheck {
    border-radius: 8px; padding: 8px 10px; font-weight: 600; font-size: 12px;
    background: #f1f5f9; color: #334155; border: 1px solid #cbd5e1;
}
QLabel#counterVoltCheck[statusLevel="ok"] {
    background: #ecfdf5; color: #065f46; border: 1px solid #6ee7b7;
}
QLabel#counterVoltCheck[statusLevel="warn"] {
    background: #fffbeb; color: #92400e; border: 1px solid #fcd34d;
}
QLabel#counterVoltCheck[statusLevel="fail"] {
    background: #fef2f2; color: #991b1b; border: 1px solid #fca5a5;
}
QLabel#counterStatusCompact {
    border-radius: 8px; padding: 8px 10px; font-weight: 600; font-size: 12px;
    background: #f1f5f9; color: #334155; border: 1px solid #cbd5e1;
}
QLabel#counterStatusCompact[statusLevel="ok"] {
    background: #ecfdf5; color: #065f46; border: 1px solid #6ee7b7;
}
QLabel#counterStatusCompact[statusLevel="warn"] {
    background: #fffbeb; color: #92400e; border: 1px solid #fcd34d;
}
QLabel#counterStatusCompact[statusLevel="fail"] {
    background: #fef2f2; color: #991b1b; border: 1px solid #fca5a5;
}
QLabel#counterStatusCompact[statusLevel="busy"] {
    background: #eff6ff; color: #1e40af; border: 1px solid #93c5fd;
}
#dayFilterLabel { font-size: 12px; font-weight: 700; color: #cbd5e1; }
#dayFilterCombo {
    min-height: 28px; font-size: 12px; font-weight: 600;
    background: #1a3a5c; color: #f8fafc; border: 1px solid #3d5a80;
}
#workflowStrip {
    background: #f0f4f9; border: 1px solid #c5d0de; border-radius: 8px;
}
#workflowStepDone {
    background: #0d5c4b; color: #fff; border-radius: 6px;
    padding: 4px 2px; font-size: 10px; font-weight: 800;
}
#workflowStepCurrent {
    background: #c45f14; color: #fff; border-radius: 6px;
    padding: 4px 2px; font-size: 10px; font-weight: 800;
}
#workflowStepPending {
    background: #e8edf3; color: #64748b; border-radius: 6px;
    padding: 4px 2px; font-size: 10px; font-weight: 700;
}
#workflowArrow { color: #94a3b8; font-size: 14px; font-weight: 700; }
#navRail {
    background: #0f2744; border-right: 1px solid #1a3a5c;
}
QPushButton#navBtn {
    background: transparent; color: #94b8d9; border: none;
    border-radius: 6px; padding: 6px 2px; font-size: 10px; font-weight: 700;
    min-height: 34px;
}
QPushButton#navBtn:hover { background: #1a3a5c; color: #fff; }
QPushButton#navBtn:checked {
    background: #c45f14; color: #fff; border: none;
}
#statTitle { font-size: 11px; font-weight: 700; color: #64748b; }
#statValue { font-size: 18px; font-weight: 800; color: #0f2744; }
#mapOptions {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px;
}
QPushButton#secondary {
    background: #f1f5f9; border: 1px solid #94a3b8; font-weight: 600;
}
QPushButton#secondary:hover { background: #e2e8f0; }
#hint { color: #64748b; font-size: 12px; }
#fieldChecks { color: #475569; font-size: 11px; line-height: 1.4; padding: 2px 0; }
#offlineHint { color: #475569; font-size: 12px; font-weight: 600; }
QLabel#counterStatus {
    border-radius: 8px; padding: 10px 12px; font-weight: 600; font-size: 13px;
    background: #f1f5f9; color: #334155; border: 1px solid #cbd5e1;
}
QLabel#counterStatus[statusLevel="ok"] {
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
QLabel#shiftSummary {
    font-size: 13px; font-weight: 700; color: #0f2744;
    background: transparent; border: none; border-radius: 0;
    padding: 4px 0;
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
#brandSub { font-size: 10px; font-weight: 600; color: #94b8d9; }
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
#mapLoadOverlay {
    background: rgba(232, 237, 243, 0.94);
    border: none;
}
#mapLoadTitle {
    font-size: 20px; font-weight: 800; color: #0f2744;
}
#mapLoadDetail {
    font-size: 13px; font-weight: 600; color: #475569;
}
QSplitter#mainSplit::handle {
    background: #c5d0de; width: 3px;
}
QSplitter#mainSplit::handle:hover { background: #c45f14; }
#pageScroll { background: #f8fafc; border: none; }
#installHeader {
    background: #ffffff; border: 1px solid #c5d0de; border-radius: 12px;
}
#installTitle { font-size: 18px; font-weight: 800; color: #0f2744; }
#installSub { font-size: 13px; font-weight: 600; color: #475569; }
#installWarn { color: #b42318; font-weight: 700; font-size: 12px; }
#installCompass { font-weight: 700; font-size: 14px; color: #0f2744; }
QLabel[role="h"] {
    font-size: 11px; font-weight: 800; color: #64748b;
    letter-spacing: 0.8px; padding-top: 4px;
}
QLabel[role="title"] { font-size: 17px; font-weight: 800; color: #0f2744; }
QPushButton {
    background: #ffffff; border: 1px solid #94a3b8; border-radius: 4px;
    padding: 4px 8px; font-weight: 600; color: #0f2744; font-size: 12px;
    min-height: 26px;
}
QPushButton:hover { background: #f1f5f9; border-color: #64748b; }
QPushButton:pressed { background: #e2e8f0; }
QPushButton:disabled { background: #e8edf3; color: #94a3b8; }
QPushButton#primary {
    background: #c45f14; color: #fff; border: none;
    font-weight: 700; padding: 4px 10px; font-size: 12px;
}
QPushButton#primary:hover { background: #a04f10; }
QPushButton#go {
    background: #0d5c4b; color: #fff; border: none;
    font-weight: 700; padding: 4px 10px; font-size: 12px;
}
QPushButton#go:hover { background: #0a4a3d; }
QPushButton#stop {
    background: #b42318; color: #fff; border: none;
    font-weight: 700; padding: 6px 10px; font-size: 13px;
}
QPushButton#stop:hover { background: #912018; }
QPushButton#fieldPrimary {
    background: #0d5c4b; color: #fff; border: none;
    font-weight: 800; padding: 10px 8px; font-size: 14px; min-height: 32px;
}
QPushButton#fieldSkip {
    background: #64748b; color: #fff; border: none;
    font-weight: 800; padding: 10px 8px; font-size: 14px; min-height: 32px;
}
QPushButton#themeBtn {
    padding: 6px 10px; font-size: 11px; min-width: 52px;
    background: #1a3a5c; color: #cbd5e1; border: 1px solid #3d5a80;
}
QPushButton#themeBtn:checked { background: #c45f14; color: #fff; border: none; }
QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    background: #ffffff; border: 1px solid #94a3b8; border-radius: 6px;
    padding: 6px 8px; color: #0f2744; font-size: 13px;
    min-height: 30px;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 2px solid #c45f14; }
QListWidget {
    background: #ffffff; border: 1px solid #c5d0de; border-radius: 8px;
}
QListWidget::item { padding: 5px 6px; border-bottom: 1px solid #eef2f7; }
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
#driveNextChip {
    font-size: 12px; font-weight: 700; color: #e8f4fc;
    background: rgba(255, 255, 255, 0.14); border-radius: 6px;
    padding: 4px 10px;
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
QGroupBox#sectionCard, QGroupBox#sectionCardCompact {
    background: #222b3a; border-color: #3d4f66; color: #cbd5e1;
}
QGroupBox#sectionCardCompact::title { color: #e2e8f0; }
#statCard, #statCardCompact { background: #222b3a; border-color: #3d4f66; }
#installHeader, #installHeaderCompact {
    background: #222b3a; border-color: #3d4f66;
}
#tabContextLine { color: #e2e8f0; }
#installChecklist { background: #1a2230; border-color: #3d4f66; color: #cbd5e1; }
#fieldChecks, #offlineHint { color: #94a3b8; }
#hint { color: #94a3b8; }
#statValue { color: #e8eaed; }
QPushButton#primary { background: #3b82f6; color: #fff; border: none; }
QPushButton#go { background: #16a34a; color: #fff; border: none; font-weight: 800; padding: 14px; }
QPushButton#stop { background: #dc2626; color: #fff; border: none; font-weight: 800; padding: 14px; }
QStatusBar { background: #0a1628; color: #cbd5e1; }
#placeholder { background: #0f141c; }
#phTitle { color: #7eb8ff; }
"""
