"""Field view themes: high-contrast Qt styles for sunlight (sunny / cloudy / night)."""

from __future__ import annotations

VALID_THEMES = ("sunny", "cloudy", "night")


def normalize_theme(raw: str | None) -> str:
    """Map saved values (incl. legacy light/dark) to sunny | cloudy | night."""
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
        return _NIGHT
    if t == "cloudy":
        return _CLOUDY
    return _SUNNY


# Warm, high-contrast — readable in direct sun (no glare-white panels).
_SUNNY = """
* { font-family: 'Segoe UI', system-ui, sans-serif; }
QMainWindow, QWidget { background: #ebe4d6; color: #0f1419; font-size: 14px; }
#topbar { background: #fff8ef; border-bottom: 2px solid #8a7f6e; }
#brand { font-size: 16px; font-weight: 800; color: #b45309; }
#sidepanel { background: #fff8ef; border-right: 2px solid #8a7f6e; }
QLabel[role="h"] { font-size: 11px; font-weight: 800; color: #5c4f3a;
                   letter-spacing: 1px; padding-top: 6px; }
QLabel[role="title"] { font-size: 16px; font-weight: 800; color: #0f1419; }
QPushButton { background: #f5ead8; border: 2px solid #6b5f4f; border-radius: 9px;
              padding: 9px 11px; font-weight: 700; color: #0f1419; }
QPushButton:hover { background: #edd9bc; }
QPushButton:pressed { background: #dcc9a8; }
QPushButton:checked { background: #b45309; color: #fff; border: 2px solid #7c2d12; }
QPushButton#primary { background: #c2410c; color: #fff; border: 2px solid #7c2d12;
                      font-weight: 800; padding: 11px; }
QPushButton#primary:hover { background: #9a3412; }
QPushButton#go { background: #15803d; color: #fff; border: 2px solid #14532d;
                 font-weight: 800; padding: 12px; font-size: 14px; }
QPushButton#go:hover { background: #166534; }
QPushButton#stop { background: #b91c1c; color: #fff; border: 2px solid #7f1d1d;
                   font-weight: 800; padding: 12px; font-size: 14px; }
QPushButton#stop:hover { background: #991b1b; }
QPushButton#fieldPrimary { background: #15803d; color: #fff; border: 3px solid #14532d;
                            font-weight: 800; padding: 16px 12px; font-size: 16px; min-height: 22px; }
QPushButton#fieldPrimary:hover { background: #166534; }
QPushButton#fieldSkip { background: #78716c; color: #fff; border: 3px solid #57534e;
                         font-weight: 800; padding: 16px 12px; font-size: 16px; min-height: 22px; }
QPushButton#fieldSkip:hover { background: #57534e; }
QPushButton#themeBtn { padding: 7px 10px; font-size: 12px; min-width: 58px; }
QPushButton#themeBtn:checked { background: #b45309; color: #fff; border: 2px solid #7c2d12; }
QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    background: #fffdf8; border: 2px solid #6b5f4f; border-radius: 8px; padding: 8px;
    color: #0f1419; font-size: 14px; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 2px solid #c2410c; }
QListWidget { background: #fffdf8; border: 2px solid #8a7f6e; border-radius: 8px; }
QListWidget::item { padding: 8px; border-bottom: 1px solid #e8dcc8; }
QListWidget::item:selected { background: #fde68a; color: #0f1419; font-weight: 700; }
QStatusBar { background: #fff8ef; border-top: 2px solid #8a7f6e; color: #0f1419; font-weight: 600; }
QScrollArea { border: none; background: #fff8ef; }
QCheckBox { font-weight: 600; spacing: 6px; }
#placeholder { background: #e0d6c4; }
#phTitle { font-size: 26px; font-weight: 800; color: #b45309; }
#phText { font-size: 14px; color: #44403c; font-weight: 600; }
"""

# Cool gray-blue — softer than sunny, still strong contrast for overcast glare.
_CLOUDY = """
* { font-family: 'Segoe UI', system-ui, sans-serif; }
QMainWindow, QWidget { background: #dce4ed; color: #0c1929; font-size: 14px; }
#topbar { background: #f1f5f9; border-bottom: 2px solid #64748b; }
#brand { font-size: 16px; font-weight: 800; color: #1d4ed8; }
#sidepanel { background: #f8fafc; border-right: 2px solid #64748b; }
QLabel[role="h"] { font-size: 11px; font-weight: 800; color: #475569;
                   letter-spacing: 1px; padding-top: 6px; }
QLabel[role="title"] { font-size: 16px; font-weight: 800; color: #0c1929; }
QPushButton { background: #e2e8f0; border: 2px solid #64748b; border-radius: 9px;
              padding: 9px 11px; font-weight: 700; color: #0c1929; }
QPushButton:hover { background: #cbd5e1; }
QPushButton:pressed { background: #b8c5d6; }
QPushButton:checked { background: #1d4ed8; color: #fff; border: 2px solid #1e3a8a; }
QPushButton#primary { background: #1d4ed8; color: #fff; border: 2px solid #1e3a8a;
                      font-weight: 800; padding: 11px; }
QPushButton#primary:hover { background: #1e40af; }
QPushButton#go { background: #047857; color: #fff; border: 2px solid #064e3b;
                 font-weight: 800; padding: 12px; font-size: 14px; }
QPushButton#go:hover { background: #065f46; }
QPushButton#stop { background: #dc2626; color: #fff; border: 2px solid #991b1b;
                   font-weight: 800; padding: 12px; font-size: 14px; }
QPushButton#stop:hover { background: #b91c1c; }
QPushButton#fieldPrimary { background: #047857; color: #fff; border: 3px solid #064e3b;
                            font-weight: 800; padding: 16px 12px; font-size: 16px; min-height: 22px; }
QPushButton#fieldPrimary:hover { background: #065f46; }
QPushButton#fieldSkip { background: #64748b; color: #fff; border: 3px solid #475569;
                         font-weight: 800; padding: 16px 12px; font-size: 16px; min-height: 22px; }
QPushButton#fieldSkip:hover { background: #475569; }
QPushButton#themeBtn { padding: 7px 10px; font-size: 12px; min-width: 58px; }
QPushButton#themeBtn:checked { background: #1d4ed8; color: #fff; border: 2px solid #1e3a8a; }
QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    background: #ffffff; border: 2px solid #64748b; border-radius: 8px; padding: 8px;
    color: #0c1929; font-size: 14px; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 2px solid #1d4ed8; }
QListWidget { background: #ffffff; border: 2px solid #94a3b8; border-radius: 8px; }
QListWidget::item { padding: 8px; border-bottom: 1px solid #e2e8f0; }
QListWidget::item:selected { background: #bfdbfe; color: #0c1929; font-weight: 700; }
QStatusBar { background: #f1f5f9; border-top: 2px solid #64748b; color: #0c1929; font-weight: 600; }
QScrollArea { border: none; background: #f8fafc; }
QCheckBox { font-weight: 600; spacing: 6px; }
#placeholder { background: #cbd5e1; }
#phTitle { font-size: 26px; font-weight: 800; color: #1d4ed8; }
#phText { font-size: 14px; color: #334155; font-weight: 600; }
"""

_NIGHT = """
* { font-family: 'Segoe UI', system-ui, sans-serif; }
QMainWindow, QWidget { background: #141820; color: #e8eaed; font-size: 13px; }
#topbar { background: #1c2330; border-bottom: 1px solid #3d4654; }
#brand { font-size: 16px; font-weight: 800; color: #7eb8ff; }
#sidepanel { background: #1c2330; border-right: 1px solid #3d4654; }
QLabel[role="h"] { font-size: 11px; font-weight: 800; color: #9aa3b2;
                   letter-spacing: 1px; padding-top: 6px; }
QLabel[role="title"] { font-size: 15px; font-weight: 800; color: #f1f3f5; }
QPushButton { background: #2a3342; border: 1px solid #4a5568; border-radius: 9px;
              padding: 9px 11px; font-weight: 600; color: #e8eaed; }
QPushButton:hover { background: #354052; }
QPushButton:pressed { background: #1f2836; }
QPushButton:checked { background: #3b82f6; color: #fff; border: none; }
QPushButton#primary { background: #3b82f6; color: #fff; border: none; font-weight: 800; padding: 11px; }
QPushButton#primary:hover { background: #2563eb; }
QPushButton#go { background: #16a34a; color: #fff; border: none; font-weight: 800; padding: 12px; font-size: 14px; }
QPushButton#go:hover { background: #15803d; }
QPushButton#stop { background: #dc2626; color: #fff; border: none; font-weight: 800; padding: 12px; font-size: 14px; }
QPushButton#stop:hover { background: #b91c1c; }
QPushButton#fieldPrimary { background: #16a34a; color: #fff; border: none;
                            font-weight: 800; padding: 16px 12px; font-size: 16px; min-height: 22px; }
QPushButton#fieldPrimary:hover { background: #15803d; }
QPushButton#fieldSkip { background: #64748b; color: #fff; border: none;
                         font-weight: 800; padding: 16px 12px; font-size: 16px; min-height: 22px; }
QPushButton#fieldSkip:hover { background: #475569; }
QPushButton#themeBtn { padding: 7px 10px; font-size: 12px; min-width: 58px; }
QPushButton#themeBtn:checked { background: #3b82f6; color: #fff; border: none; }
QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    background: #252e3d; border: 1px solid #4a5568; border-radius: 8px; padding: 7px; color: #e8eaed; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 1px solid #3b82f6; }
QListWidget { background: #252e3d; border: 1px solid #3d4654; border-radius: 8px; color: #e8eaed; }
QListWidget::item { padding: 7px; border-bottom: 1px solid #2a3342; }
QListWidget::item:selected { background: #1e3a5f; color: #e8eaed; }
QStatusBar { background: #1c2330; border-top: 1px solid #3d4654; color: #e8eaed; }
QScrollArea { border: none; background: #1c2330; }
QCheckBox { color: #e8eaed; }
#placeholder { background: #1a1f28; }
#phTitle { font-size: 26px; font-weight: 800; color: #7eb8ff; }
#phText { font-size: 14px; color: #9aa3b2; }
"""
