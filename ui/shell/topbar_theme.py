"""Shell theme helpers — P46 E1.5 tail from main.py."""

from __future__ import annotations

from ui_themes import normalize_theme, qt_stylesheet


class ShellThemeMixin:
    # ------------------------------------------------------------- view theme
    def _sync_theme_buttons(self):
        t = normalize_theme(self.state.theme)
        for key, btn in self._theme_btns.items():
            btn.setChecked(key == t)

    def _refresh_theme_labels(self):
        t = normalize_theme(self.state.theme)
        if t == "night":
            sub, hint, warn, on = "#9aa3b2", "#9aa3b2", "#f87171", "#4ade80"
        elif t == "cloudy":
            sub, hint, warn, on = "#475569", "#475569", "#b91c1c", "#047857"
        else:
            sub, hint, warn, on = "#5c4f3a", "#5c4f3a", "#b91c1c", "#15803d"
        if hasattr(self, "lbl_save_hint"):
            self.lbl_save_hint.setStyleSheet(f"color:{hint};font-size:12px;font-weight:600;")
        if hasattr(self, "lbl_compass_sub"):
            self.lbl_compass_sub.setStyleSheet(f"color:{sub};font-size:12px;")
        if hasattr(self, "lbl_street_warn"):
            self.lbl_street_warn.setStyleSheet(f"color:{warn};font-weight:700;")
        if hasattr(self, "lbl_offline") and self.state.offline_mode:
            self.lbl_offline.setStyleSheet(f"color:{on};font-weight:700;")

    def _set_view_theme(self, theme: str):
        t = normalize_theme(theme)
        if t == normalize_theme(self.state.theme):
            self._sync_theme_buttons()
            return
        self.state.theme = t
        self.setStyleSheet(qt_stylesheet(t))
        self._sync_theme_buttons()
        self._refresh_theme_labels()
        self._refresh_offline_ui()
        self.state.save()
        labels = {"sunny": "Sunny — panel theme (map stays Protomaps default)",
                  "cloudy": "Cloudy — panel theme",
                  "night": "Night — panel theme"}
        self.statusBar().showMessage(labels.get(t, t), 5000)

    def _info(self, msg):
        QMessageBox.information(self, "Traffic Deployer", msg)

    def _warn(self, msg):
        QMessageBox.warning(self, "Traffic Deployer", msg)
