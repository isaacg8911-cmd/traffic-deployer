"""Reusable Qt widgets for Traffic Deployer shell."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.simple_mode import COMPACT_UI
from ui.spacing import (
    GRID_GAP,
    ROW_GAP,
    apply_card_layout,
    apply_page_layout,
    apply_row,
    apply_section_layout,
)


class WorkflowStrip(QFrame):
    """Horizontal step indicator for Setup workflow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workflowStrip")
        self._lay = QHBoxLayout(self)
        pad = 6 if COMPACT_UI else 8
        self._lay.setContentsMargins(pad, pad, pad, pad)
        self._lay.setSpacing(ROW_GAP)
        self._labels: list[QLabel] = []

    def set_steps(self, steps: list[dict]) -> None:
        while self._labels:
            w = self._labels.pop()
            self._lay.removeWidget(w)
            w.deleteLater()
        for i, step in enumerate(steps):
            lbl = QLabel(step["label"])
            lbl.setObjectName(f"workflowStep{step['status'].title()}")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setMinimumWidth(48 if COMPACT_UI else 52)
            self._lay.addWidget(lbl, 1)
            self._labels.append(lbl)
            if i < len(steps) - 1:
                arr = QLabel("›")
                arr.setObjectName("workflowArrow")
                arr.setAlignment(Qt.AlignCenter)
                self._lay.addWidget(arr)


def page_column(parent: QWidget | None = None) -> tuple[QWidget, QVBoxLayout]:
    """Standard page root with unified margins and vertical rhythm."""
    w = QWidget(parent)
    w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    lay = QVBoxLayout(w)
    apply_page_layout(lay)
    return w, lay


def button_row(parent_layout: QVBoxLayout, *widgets: QWidget, stretch_last: bool = False) -> QHBoxLayout:
    """Horizontal action row that won't squash buttons below readable size."""
    row = QHBoxLayout()
    apply_row(row)
    for i, widget in enumerate(widgets):
        widget.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        grow = stretch_last and i == len(widgets) - 1
        row.addWidget(widget, 1 if grow else 0)
    parent_layout.addLayout(row)
    return row


def button_stack(parent_layout: QVBoxLayout, *widgets: QWidget) -> None:
    """Full-width buttons stacked vertically — for narrow side panels."""
    for widget in widgets:
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        parent_layout.addWidget(widget)


def section_group(
    title: str,
    parent_layout: QVBoxLayout,
    stretch: int = 0,
    *,
    object_name: str | None = None,
    compact: bool | None = None,
) -> QVBoxLayout:
    """Card-style group; returns inner layout for section contents."""
    tight = COMPACT_UI if compact is None else compact
    box = QGroupBox(title)
    box.setObjectName(object_name or ("sectionCardCompact" if tight else "sectionCard"))
    box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    inner = QVBoxLayout(box)
    apply_section_layout(inner)
    parent_layout.addWidget(box, stretch)
    return inner


def stat_card(title: str, value: str = "—") -> tuple[QFrame, QLabel]:
    """Metric tile for Route tab."""
    card = QFrame()
    card.setObjectName("statCardCompact" if COMPACT_UI else "statCard")
    lay = QVBoxLayout(card)
    apply_card_layout(lay)
    t = QLabel(title)
    t.setObjectName("statTitle")
    v = QLabel(value)
    v.setObjectName("statValue")
    lay.addWidget(t)
    lay.addWidget(v)
    return card, v
