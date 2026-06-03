"""Floating route-pick order panel — live list, reorder, remove."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


class RoutePickOrderDialog(QDialog):
    """Non-modal window listing picks as you build the route."""

    order_changed = Signal(list)  # list of uids in order

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Route order — your picks")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(360)
        self.setMinimumHeight(280)
        self._syncing = False

        layout = QVBoxLayout(self)
        self.lbl_hint = QLabel(
            "Stops appear here as you pick. Drag to reorder, or use Up/Down/Remove.")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setObjectName("hint")
        layout.addWidget(self.lbl_hint)

        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.model().rowsMoved.connect(self._emit_order_from_list)
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.btn_up = QPushButton("Up")
        self.btn_up.setObjectName("secondary")
        self.btn_up.clicked.connect(self._move_up)
        self.btn_down = QPushButton("Down")
        self.btn_down.setObjectName("secondary")
        self.btn_down.clicked.connect(self._move_down)
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setObjectName("secondary")
        self.btn_remove.clicked.connect(self._remove_selected)
        row.addWidget(self.btn_up)
        row.addWidget(self.btn_down)
        row.addWidget(self.btn_remove)
        layout.addLayout(row)

        self.lbl_count = QLabel("0 stops chosen")
        self.lbl_count.setObjectName("hint")
        layout.addWidget(self.lbl_count)

    def _renumber_item_labels(self) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            if not item:
                continue
            text = item.text()
            if ". " in text:
                _, rest = text.split(". ", 1)
                item.setText(f"{i + 1}. {rest}")

    def _emit_order_from_list(self) -> None:
        if self._syncing:
            return
        self._renumber_item_labels()
        uids = self._uids_from_list()
        self.order_changed.emit(uids)
        self._update_count(len(uids))

    def _uids_from_list(self) -> list[str]:
        out: list[str] = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item:
                uid = item.data(Qt.ItemDataRole.UserRole)
                if uid:
                    out.append(str(uid))
        return out

    def _update_count(self, n: int) -> None:
        total = getattr(self, "_total_stops", 0)
        if total:
            self.lbl_count.setText(f"{n} of {total} stops in your order")
        else:
            self.lbl_count.setText(f"{n} stop(s) chosen")

    def sync_from_parent(
        self,
        *,
        uids: list[str],
        stops_by_uid: dict,
        letters: dict[str, str],
        street_label,
        total: int,
        prompt: str,
    ) -> None:
        self._total_stops = total
        self._syncing = True
        self.list.clear()
        for i, uid in enumerate(uids):
            s = stops_by_uid.get(uid)
            if not s:
                continue
            letter = letters.get(uid, "?")
            text = (
                f"{i + 1}. [{letter}] Site {s.get('id', '')} — "
                f"{street_label(s)}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, uid)
            self.list.addItem(item)
        self._syncing = False
        self.lbl_hint.setText(prompt or "Pick the next site on the map or dropdown.")
        self._update_count(len(uids))
        self.btn_up.setEnabled(len(uids) > 0)
        self.btn_down.setEnabled(len(uids) > 0)
        self.btn_remove.setEnabled(len(uids) > 0)

    def _move_up(self) -> None:
        row = self.list.currentRow()
        if row <= 0:
            return
        item = self.list.takeItem(row)
        self.list.insertItem(row - 1, item)
        self.list.setCurrentRow(row - 1)
        self._emit_order_from_list()

    def _move_down(self) -> None:
        row = self.list.currentRow()
        if row < 0 or row >= self.list.count() - 1:
            return
        item = self.list.takeItem(row)
        self.list.insertItem(row + 1, item)
        self.list.setCurrentRow(row + 1)
        self._emit_order_from_list()

    def _remove_selected(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        self.list.takeItem(row)
        self._emit_order_from_list()
