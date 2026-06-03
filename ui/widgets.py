"""Reusable Qt widgets for Traffic Deployer shell."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class WorkflowStrip(QFrame):
    """Horizontal step indicator for Setup workflow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workflowStrip")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(8, 8, 8, 8)
        self._lay.setSpacing(6)
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
            lbl.setMinimumWidth(52)
            self._lay.addWidget(lbl, 1)
            self._labels.append(lbl)
            if i < len(steps) - 1:
                arr = QLabel("›")
                arr.setObjectName("workflowArrow")
                arr.setAlignment(Qt.AlignCenter)
                self._lay.addWidget(arr)


def section_group(
    title: str,
    parent_layout: QVBoxLayout,
    stretch: int = 0,
    *,
    object_name: str | None = None,
) -> QVBoxLayout:
    """Card-style group; returns inner layout for section contents."""
    box = QGroupBox(title)
    box.setObjectName(object_name or "sectionCard")
    inner = QVBoxLayout(box)
    inner.setContentsMargins(12, 14, 12, 12)
    inner.setSpacing(8)
    parent_layout.addWidget(box, stretch)
    return inner


def stat_card(title: str, value: str = "—") -> tuple[QFrame, QLabel]:
    """Metric tile for Route tab."""
    card = QFrame()
    card.setObjectName("statCard")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(12, 10, 12, 10)
    t = QLabel(title)
    t.setObjectName("statTitle")
    v = QLabel(value)
    v.setObjectName("statValue")
    lay.addWidget(t)
    lay.addWidget(v)
    return card, v
