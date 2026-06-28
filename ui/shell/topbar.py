"""Shell topbar + page navigation — P46 E1.5 extract from main.py."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import road_router
from core import counter_inventory
from core.field_ready import check_all
from ui import workflow as setup_workflow
from ui.paths import APP_DIR, DATA_DIR, IS_PORTABLE
from ui.simple_mode import COMPACT_UI, FIELD_NAV_INDICES, FIELD_SHELL, HIDE_PANEL_THEMES, SIMPLE_MODE
from ui.threads import SmokeTestThread
from version import APP_NAME, APP_VERSION, APP_TAGLINE


class ShellTopbarMixin:
    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 6, 12, 6)
        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand = QLabel(APP_NAME)
        brand.setObjectName("brand")
        self.brand_sub = QLabel(f"v{APP_VERSION}  ·  home setup · Wi‑Fi tools on")
        self.brand_sub.setObjectName("brandSub")
        brand_col.addWidget(brand)
        brand_col.addWidget(self.brand_sub)
        lay.addLayout(brand_col)
        lay.addStretch(1)

        mode_wrap = QWidget()
        mode_wrap.setObjectName("modeBar")
        mode_lay = QHBoxLayout(mode_wrap)
        mode_lay.setContentsMargins(0, 0, 0, 0)
        mode_lay.setSpacing(6)
        self.lbl_mode_pill = QLabel("ONLINE")
        self.lbl_mode_pill.setObjectName("modePill")
        self.btn_mode_online = QPushButton("I'm online")
        self.btn_mode_online.setObjectName("modeBtnOnline")
        self.btn_mode_online.setCheckable(True)
        self.btn_mode_online.clicked.connect(self._on_mode_online)
        self.btn_mode_offline = QPushButton("Go offline")
        self.btn_mode_offline.setObjectName("modeBtnOffline")
        self.btn_mode_offline.setCheckable(True)
        self.btn_mode_offline.clicked.connect(self._on_mode_offline)
        mode_lay.addWidget(self.lbl_mode_pill)
        mode_lay.addWidget(self.btn_mode_online)
        mode_lay.addWidget(self.btn_mode_offline)
        lay.addWidget(mode_wrap)
        self._day_filter_wrap = QWidget()
        self._day_filter_wrap.setObjectName("dayFilterBar")
        day_lay = QHBoxLayout(self._day_filter_wrap)
        day_lay.setContentsMargins(0, 0, 0, 0)
        day_lay.setSpacing(6)
        day_lbl = QLabel("Sites")
        day_lbl.setObjectName("dayFilterLabel")
        self.combo_day = QComboBox()
        self.combo_day.setObjectName("dayFilterCombo")
        self.combo_day.setMinimumWidth(108)
        self.combo_day.currentTextChanged.connect(self._on_day_filter_changed)
        day_lay.addWidget(day_lbl)
        day_lay.addWidget(self.combo_day)
        self._day_filter_wrap.hide()
        lay.addWidget(self._day_filter_wrap)
        lay.addSpacing(8)
        self.btn_drive_arrived = QPushButton("ARRIVED → Install")
        self.btn_drive_arrived.setObjectName("driveArrived")
        self.btn_drive_arrived.clicked.connect(self._drive_arrived_install)
        self.btn_drive_arrived.hide()
        lay.addWidget(self.btn_drive_arrived)
        self.btn_drive_end = QPushButton("Stop driving")
        self.btn_drive_end.setObjectName("secondary")
        self.btn_drive_end.clicked.connect(self._stop_drive)
        self.btn_drive_end.hide()
        lay.addWidget(self.btn_drive_end)
        lay.addSpacing(8)

        b_about = QPushButton("About")
        b_about.setObjectName("aboutBtn")
        b_about.clicked.connect(self._show_about)
        lay.addWidget(b_about)
        lay.addSpacing(12)
        theme_wrap = QWidget()
        theme_wrap.setObjectName("themeBar")
        theme_lay = QHBoxLayout(theme_wrap)
        theme_lay.setContentsMargins(0, 0, 0, 0)
        theme_lay.setSpacing(4)
        self._theme_btns: dict[str, QPushButton] = {}
        for key, label in (("sunny", "Sunny"), ("cloudy", "Cloudy"), ("night", "Night")):
            tb = QPushButton(label)
            tb.setObjectName("themeBtn")
            tb.setCheckable(True)
            tb.clicked.connect(lambda _=False, k=key: self._set_view_theme(k))
            theme_lay.addWidget(tb)
            self._theme_btns[key] = tb
        self._theme_wrap = theme_wrap
        if HIDE_PANEL_THEMES:
            theme_wrap.hide()
        lay.addWidget(theme_wrap)
        from ui.simple_mode import COMPACT_UI
        if COMPACT_UI:
            self.brand_sub.hide()
        return bar

    def _show_about(self):
        maps = "Yes" if os.path.isfile(os.path.join(DATA_DIR, "california.pmtiles")) else "No — run setup_maps.py"
        roads = "Yes" if road_router.has_graph(DATA_DIR) else "No — download in Setup"
        QMessageBox.information(
            self, APP_NAME,
            f"<b>{APP_NAME} v{APP_VERSION}</b><br><br>"
            f"{APP_TAGLINE}<br><br>"
            f"<b>Offline basemap:</b> {maps}<br>"
            f"<b>Road routing graph:</b> {roads}<br><br>"
            f"Profile: {self.state.profile}<br>"
            f"Smoke test: <code>scripts\\smoke.bat</code>",
        )

    def _go_page(self, i: int):
        if FIELD_SHELL and self.state.offline_mode and i not in FIELD_NAV_INDICES:
            self.statusBar().showMessage(
                "Field mode — Route, Install, Pickup, Audit. Tap I'm online at home for Setup.",
                5000,
            )
            return
        if self._gps_follow and i not in (1, 2):
            self.statusBar().showMessage(
                "Following GPS — tap ARRIVED or Stop follow first.", 5000)
            return
        if self.pages.currentIndex() == 2 and i != 2:
            self._flush_install_form()
            self._end_manual_grab(silent=True)
        self.pages.setCurrentIndex(i)
        for j in range(5):
            getattr(self, f"_navbtn_{j}").setChecked(j == i)
        if i == 0:
            self.spin_lat.setValue(self.state.home[0])
            self.spin_lon.setValue(self.state.home[1])
            self._refresh_workflow_strip()
            counter_inventory.sync_from_shift(self.state.stops)
            self._refresh_counter_inventory()
        elif i == 1:
            self._refresh_route_list()
        elif i == 2:
            self._counter_list_ports()
            self._refresh_install()
            QTimer.singleShot(350, self._counter_auto_connect)
        elif i == 3:
            self._refresh_pickup()
        elif i == 4:
            self._refresh_audit()
        self._refresh_field_alerts()
        self._update_right()
        self._push_state()

    def _update_right(self, force_map: bool = False):
        show_map = (
            force_map
            or self._gps_follow
            or bool(self.state.stops)
            or bool(getattr(self, "_map_preview_stops", None))
        )
        was_hidden = self.right_stack.currentIndex() == 0
        self.right_stack.setCurrentIndex(1 if show_map else 0)
        if show_map and (was_hidden or force_map) and self.state.stops:
            QTimer.singleShot(250, self._refresh_map_view)

    def _refresh_workflow_strip(self):
        if SIMPLE_MODE or not getattr(self, "workflow_strip", None):
            return
        miles = float(self.state.route.get("miles", 0) or 0)
        self.workflow_strip.set_steps(setup_workflow.compute_workflow(
            home=tuple(self.state.home),
            default_home=self.state.default_home,
            excel_paths=self.excel_paths,
            est_paths=self.est_paths,
            has_graph=road_router.has_graph(DATA_DIR),
            route_miles=miles,
            offline_mode=bool(self.state.offline_mode),
        ))

    def _refresh_field_ready(self):
        if not hasattr(self, "lbl_field_score"):
            return
        gps_snap = self.gps.latest() if hasattr(self, "gps") else None
        r = check_all(
            APP_DIR,
            probe_gps=gps_snap is None,
            probe_counter=True,
            gps_snapshot=gps_snap,
            stop_server_after=False,
        )
        score = r["score"]
        from ui.simple_mode import COMPACT_UI
        if score >= 88:
            color, tag = "#15803d", "READY FOR FIELD"
        elif score >= 70:
            color, tag = "#b45309", "READY WITH WARNINGS"
        else:
            color, tag = "#b91c1c", "FIX BEFORE FIELD"
        if COMPACT_UI:
            self.lbl_field_score.setText(f"{tag} · {score}/100")
            self.lbl_field_score.setStyleSheet(
                f"font-weight:800;font-size:13px;color:{color};")
            bad = [it for it in r["items"] if it["level"] != "ok"]
            if bad:
                lines = [
                    f"{'✗' if it['level'] == 'fail' else '!'} {it['label']}"
                    for it in bad[:5]
                ]
            else:
                lines = ["✓ All checks passed"]
        else:
            self.lbl_field_score.setText(f"{tag} — {score}/100")
            self.lbl_field_score.setStyleSheet(
                f"font-weight:800;font-size:15px;color:{color};")
            lines = []
            for it in r["items"]:
                if it["level"] == "ok":
                    sym = "✓"
                elif it["level"] == "warn":
                    sym = "!"
                else:
                    sym = "✗"
                extra = f" — {it['detail']}" if it.get("detail") and it["level"] != "ok" else ""
                lines.append(f"{sym} {it['label']}{extra}")
        self.lbl_field_checks.setText("\n".join(lines))
        self._field_report = r
        self._refresh_workflow_strip()
        self._refresh_field_strip_ui()

    def _maybe_field_startup_dialog(self):
        if self.state.offline_mode and self.state.stops:
            return
        r = getattr(self, "_field_report", None) or check_all(APP_DIR, probe_gps=True)
        if r.get("fail_count", 0) == 0:
            if r.get("warn_count", 0) and not self.state.stops:
                self.statusBar().showMessage(
                    "Field readiness: warnings on Setup tab — review before you leave.", 12000)
            return
        crit = [i for i in r["items"] if i["level"] == "fail"]
        body = "\n".join(f"• {i['label']}: {i.get('detail', 'missing')}" for i in crit)
        QMessageBox.warning(
            self, "Fix before field",
            f"Critical items need attention:\n\n{body}\n\n"
            "Open Setup → Field Readiness for details.\n"
            + (
                "Map 404? Re-extract the full zip — _internal/web must be beside the exe."
                if IS_PORTABLE
                else "Run setup_maps.py on WiFi if the offline map is missing."
            ),
        )

    def _run_smoke_test(self):
        if getattr(self, "_smoke_thread", None) and self._smoke_thread.isRunning():
            self.statusBar().showMessage("Smoke test already running…", 3000)
            return
        self.statusBar().showMessage("Running smoke test… (app stays responsive)", 5000)
        thread = SmokeTestThread()
        self._smoke_thread = thread

        def done(code: int, out: str):
            self._smoke_thread = None
            if code == 0:
                self._info("Smoke test PASSED.\n\n" + out[-1200:])
                self.statusBar().showMessage("Smoke test passed.", 6000)
            else:
                self._warn("Smoke test FAILED.\n\n" + out[-2000:])
            self._refresh_field_ready()

        thread.finished_result.connect(done)
        thread.start()
