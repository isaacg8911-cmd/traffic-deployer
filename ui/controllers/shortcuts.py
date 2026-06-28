"""Undo, keyboard shortcuts, and phone nav links — P46 E1.5."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import QFileDialog

from core import maps_links
from ui.paths import DATA_DIR, UNDO_FIELDS


class ShortcutsControllerMixin:
    # ------------------------------------------------------- Undo / shortcuts
    @staticmethod
    def _snapshot_stop(s: dict) -> dict:
        return {k: s.get(k) for k in UNDO_FIELDS}

    def _push_undo(self, kind: str, uid: str, snapshot: dict, **extra):
        self._undo_stack.append({"kind": kind, "uid": uid, "snapshot": snapshot, **extra})
        if len(self._undo_stack) > 20:
            self._undo_stack.pop(0)
        self._refresh_undo_ui()

    def _refresh_undo_ui(self):
        enabled = bool(self._undo_stack)
        tip = ""
        if self._undo_stack:
            last = self._undo_stack[-1]
            tip = f"Undo {last['kind']} — Site {last.get('site_id', '?')}"
        for attr in ("btn_undo_install", "btn_undo_pickup"):
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setEnabled(enabled)
                btn.setToolTip(tip)

    def _undo_last_action(self):
        if not self._undo_stack:
            return
        entry = self._undo_stack.pop()
        idx = self.state.index_of(entry["uid"])
        if idx < 0:
            self._warn("That stop is no longer in the route.")
            self._refresh_undo_ui()
            return
        s = self.state.stops[idx]
        s.update(entry["snapshot"])
        kind = entry["kind"]
        if kind in ("install", "skip"):
            self.current_index = entry.get("current_index", idx)
            self._go_page(2)
            self._refresh_install()
            self._center_current()
        elif kind == "pickup":
            self.pickup_index = entry.get("pickup_index", 0)
            self._go_page(3)
            self._refresh_pickup()
        self._persist_shift(quiet=True)
        self._push_state()
        self._refresh_route_list()
        self._refresh_audit()
        self._refresh_undo_ui()
        self.statusBar().showMessage(
            f"Undid {kind} on Site {entry.get('site_id', '')}.", 6000)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Z"), self, self._undo_last_action)
        QShortcut(QKeySequence("I"), self, self._shortcut_install)
        QShortcut(QKeySequence("S"), self, self._shortcut_skip)
        QShortcut(QKeySequence("G"), self, self._shortcut_grab_gps)
        QShortcut(QKeySequence("M"), self, self._shortcut_manual_grab)
        QShortcut(QKeySequence("N"), self, self._shortcut_prev_stop)
        QShortcut(QKeySequence("P"), self, self._shortcut_next_stop)

    def _shortcut_install(self):
        if self.pages.currentIndex() == 2:
            self._commit_install(True)

    def _shortcut_skip(self):
        if self.pages.currentIndex() == 2:
            self._commit_install(False)

    def _shortcut_grab_gps(self):
        if self.pages.currentIndex() == 2:
            self._grab_gps_here()

    def _shortcut_manual_grab(self):
        if self.pages.currentIndex() == 2:
            self._toggle_manual_grab()

    def _shortcut_prev_stop(self):
        if self.pages.currentIndex() == 2:
            self._nav_install(-1)
        elif self.pages.currentIndex() == 3:
            self._nav_pickup(-1)

    def _shortcut_next_stop(self):
        if self.pages.currentIndex() == 2:
            self._nav_install(1)
        elif self.pages.currentIndex() == 3:
            self._nav_pickup(1)

    def _phone_nav_links(self, kind: str = "install") -> tuple[list[dict], list[str]]:
        if not self.state.stops:
            return [], ["Build your route first (Setup → BUILD ROUTE)."]
        if kind == "pickup":
            batch = maps_links.pickup_sequence_stops(self.state.stops)
            if not batch:
                return [], ["No installed sites yet — install counters first."]
        else:
            batch = maps_links.install_sequence_stops(self.state.stops)
        return maps_links.build_route_links(batch)

    def _save_nav_links_page(self, kind: str) -> None:
        links, errors = self._phone_nav_links(kind)
        if errors and not links:
            self._warn("Cannot build phone links:\n\n" + "\n".join(errors))
            return
        miles = float(self.state.route.get("miles", 0) or 0)
        body = maps_links.to_html(
            links,
            profile=self.state.profile,
            miles=miles if miles > 0 and kind == "install" else None,
            kind=kind,
        )
        default = maps_links.default_links_path(DATA_DIR, self.state.profile, kind=kind)
        dlg_title = "Save install navigation links" if kind == "install" else "Save pickup navigation links"
        path, _ = QFileDialog.getSaveFileName(self, dlg_title, default, "Web page (*.html)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        msg = f"Saved {len(links)} stop link(s).\n\n{path}"
        if errors:
            msg += "\n\nSkipped:\n" + "\n".join(errors)
        msg += "\n\nTip: send this file to your phone and tap each stop (Google Maps needs Wi‑Fi or cellular)."
        if not self._internet_allowed():
            msg += "\n\nField mode — links open on your phone when it has network."
        self._info(msg)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _save_install_nav_links(self) -> None:
        self._save_nav_links_page("install")

    def _save_pickup_nav_links(self) -> None:
        self._save_nav_links_page("pickup")
