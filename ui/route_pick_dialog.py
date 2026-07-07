"""Floating route-pick order panel — live list, reorder, remove."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
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


class _ReorderList(QListWidget):
    """List whose drag-to-reorder reliably reports the new order.

    QListWidget's InternalMove implements a drop as insert-copy + remove-source,
    so QAbstractItemModel.rowsMoved is never emitted. A handler wired only to
    rowsMoved therefore misses drag reorders: the list looks reordered but the
    owner keeps the old order. dropEvent fires on every real drop, so we emit
    the settled order from here (deferred so the model has finished the move).
    """

    dropped = Signal()

    def dropEvent(self, event):
        super().dropEvent(event)
        QTimer.singleShot(0, self.dropped.emit)


class RoutePickOrderDialog(QDialog):
    """Non-modal window listing picks as you build the route."""

    order_changed = Signal(list)  # list of uids in order
    apply_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Route order — click map to add")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(360)
        self.setMinimumHeight(280)
        self._syncing = False

        layout = QVBoxLayout(self)
        self.lbl_hint = QLabel(
            "Your picks appear here as you click the map. "
            "Blue = begin, red = end. Drag to reorder.")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setObjectName("hint")
        layout.addWidget(self.lbl_hint)

        self.list = _ReorderList(self)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # QListWidget InternalMove drops are insert+remove, so model().rowsMoved
        # never fires — keep it for platforms that do emit it, but the real
        # commit path for drag-to-reorder is _ReorderList.dropEvent below.
        self.list.model().rowsMoved.connect(self._emit_order_from_list)
        self.list.dropped.connect(self._on_list_dropped)
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

        self.btn_apply = QPushButton("Apply route")
        self.btn_apply.setObjectName("primary")
        self.btn_apply.setToolTip(
            "Lock in this order and trace the route on real streets.")
        self.btn_apply.clicked.connect(self.apply_requested.emit)
        self.btn_apply.setEnabled(False)
        layout.addWidget(self.btn_apply)

    def showEvent(self, event):
        parent = self.parent()
        if parent is not None:
            ss = parent.styleSheet()
            if ss:
                self.setStyleSheet(ss)
        super().showEvent(event)

    def _renumber_item_labels(self) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            if not item:
                continue
            text = item.text()
            if ". " in text:
                _, rest = text.split(". ", 1)
                item.setText(f"{i + 1}. {rest}")

    def _on_list_dropped(self) -> None:
        """Commit order after a drag-drop reorder (see _ReorderList)."""
        if self._syncing:
            return
        self._emit_order_from_list()

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
        self.btn_apply.setEnabled(n > 0 and n >= total)
        if total and n >= total:
            self.btn_apply.setText("Apply route — all stops set")
        elif total:
            self.btn_apply.setText(f"Apply route ({n}/{total})")
        else:
            self.btn_apply.setText("Apply route")

    def sync_from_parent(
        self,
        *,
        uids: list[str],
        stops_by_uid: dict,
        letters: dict[str, str],
        street_label,
        total: int,
        prompt: str,
        pick_sides: dict[str, str] | None = None,
    ) -> None:
        self._total_stops = total
        sides = pick_sides or {}
        self._syncing = True
        self.list.clear()
        for i, uid in enumerate(uids):
            s = stops_by_uid.get(uid)
            if not s:
                continue
            letter = letters.get(uid, "?")
            side = sides.get(uid)
            side_tag = f" · {side}" if side in ("begin", "end") else ""
            text = (
                f"{i + 1}. [{letter}] Site {s.get('id', '')}{side_tag} — "
                f"{street_label(s)}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, uid)
            self.list.addItem(item)
        self._syncing = False
        self.lbl_hint.setText(prompt or "Click the next site on the map (blue or red dot).")
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
