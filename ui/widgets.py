"""Reusable Qt widgets for Traffic Deployer shell."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
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


def page_with_footer() -> tuple[QWidget, QVBoxLayout, QVBoxLayout, QWidget]:
    """Scrolling job column plus a commit bar that stays on screen."""
    outer = QWidget()
    outer.setProperty("ownsScroll", True)
    outer_lay = QVBoxLayout(outer)
    outer_lay.setContentsMargins(0, 0, 0, 0)
    outer_lay.setSpacing(0)
    scroll = QScrollArea()
    scroll.setObjectName("pageScroll")
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setFrameShape(QFrame.NoFrame)
    inner, inner_lay = page_column()
    inner.setMinimumWidth(300)
    scroll.setWidget(inner)
    footer = QWidget()
    footer.setObjectName("pageFooter")
    foot = QVBoxLayout(footer)
    apply_page_layout(foot)
    outer_lay.addWidget(scroll, 1)
    outer_lay.addWidget(footer)
    return outer, inner_lay, foot, footer


def more_body() -> tuple[QWidget, QVBoxLayout]:
    """Hidden tool stack. Call attach_more when the page is ready to place it."""
    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(ROW_GAP)
    body.hide()
    return body, lay


def attach_more(parent_layout: QVBoxLayout, body: QWidget, on_toggle=None) -> QPushButton:
    """Place Show more, then the tool stack, at the end of the job column."""
    toggle = QPushButton("Show more")
    toggle.setObjectName("secondary")
    toggle.setCheckable(True)

    def _toggle(checked: bool) -> None:
        body.setVisible(checked)
        toggle.setText("Hide more" if checked else "Show more")
        if on_toggle is not None:
            on_toggle(checked)

    toggle.toggled.connect(_toggle)
    parent_layout.addWidget(toggle)
    parent_layout.addWidget(body)
    return toggle


def more_panel(parent_layout: QVBoxLayout) -> tuple[QPushButton, QVBoxLayout]:
    """Collapsed extra tools. The returned layout is where those tools go."""
    body, lay = more_body()
    toggle = attach_more(parent_layout, body)
    return toggle, lay


def step_block(parent_layout: QVBoxLayout) -> tuple[QWidget, QVBoxLayout]:
    """One setup step that can be shown or hidden as a unit."""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(ROW_GAP)
    parent_layout.addWidget(box)
    return box, lay


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


def section_heading(
    title: str,
    parent_layout: QVBoxLayout,
    *,
    step: int | None = None,
    object_name: str = "sectionHeading",
) -> QLabel:
    """Bold flat section title — no card chrome."""
    text = f"{step}. {title}" if step is not None else title
    lbl = QLabel(text)
    lbl.setObjectName(object_name)
    parent_layout.addWidget(lbl)
    return lbl


def numbered_section(
    step: int,
    title: str,
    parent_layout: QVBoxLayout,
    *,
    step_id: str | None = None,
) -> tuple[QVBoxLayout, QLabel]:
    """Numbered workflow step — flat header + content column."""
    header = section_heading(title, parent_layout, step=step, object_name="stepHeader")
    if step_id:
        header.setProperty("stepId", step_id)
    body = QVBoxLayout()
    body.setContentsMargins(0, 0, 0, 0)
    body.setSpacing(ROW_GAP)
    parent_layout.addLayout(body)
    return body, header


def section_group(
    title: str,
    parent_layout: QVBoxLayout,
    stretch: int = 0,
    *,
    object_name: str | None = None,
    compact: bool | None = None,
) -> QVBoxLayout:
    """Section group; compact mode uses flat divider style."""
    tight = COMPACT_UI if compact is None else compact
    box = QGroupBox(title)
    if object_name:
        box.setObjectName(object_name)
    elif tight:
        box.setObjectName("sectionFlat")
    else:
        box.setObjectName("sectionCard")
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
