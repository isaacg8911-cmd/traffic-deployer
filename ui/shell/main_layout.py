"""Main window shell layout (nav rail, pages, map split) — P46 extract from main.py."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

import road_router
from ui.page_indices import NAV_PAGE_COUNT
from ui.pages import audit_page, install_page, inventory_page, pickup_page, route_page, setup_page
from ui.paths import DATA_DIR
from ui.simple_mode import FIELD_NAV_INDICES, FIELD_SHELL
from ui.spacing import NAV_GAP, NAV_PAD_H, NAV_PAD_V, NAV_WIDTH, SIDE_MAX, SIDE_MIN, SPLIT_DEFAULT
from version import APP_NAME, APP_TAGLINE


class ShellLayoutMixin:
    def _apply_field_nav_shell(self) -> None:
        """Hide Setup in nav when offline field shell is active."""
        if not FIELD_SHELL:
            return
        on_field = bool(self.state.offline_mode)
        for i in range(NAV_PAGE_COUNT):
            btn = getattr(self, f"_navbtn_{i}", None)
            if btn is None:
                continue
            if on_field:
                btn.setVisible(i in FIELD_NAV_INDICES)
            else:
                btn.setVisible(True)
        if on_field and self.pages.currentIndex() not in FIELD_NAV_INDICES:
            self._go_page(1)
        self._apply_field_desk_chrome()

    def _apply_field_desk_chrome(self) -> None:
        """Hide desk-only controls on the truck and trim home setup on work laptops."""
        on_field = bool(self.state.offline_mode)
        wl = bool(getattr(self, "_work_laptop", False))

        about = getattr(self, "btn_about", None)
        if about is not None:
            about.setVisible(not on_field and not wl)

        has_map = os.path.isfile(os.path.join(DATA_DIR, "california.pmtiles"))
        has_graph = road_router.has_graph(DATA_DIR)

        if hasattr(self, "btn_download_basemap"):
            self.btn_download_basemap.setVisible(not has_map and not on_field)
        if hasattr(self, "btn_download_roads"):
            self.btn_download_roads.setVisible(not has_graph and not on_field)
        if hasattr(self, "btn_test_wifi"):
            self.btn_test_wifi.setVisible(not on_field and not wl)
        for attr in ("btn_start_fresh", "btn_clear_shift"):
            w = getattr(self, attr, None)
            if w is not None:
                w.setVisible(not on_field and not wl)

    def _init_map_load_overlay(self) -> None:
        mf = getattr(self, "_map_frame", None)
        if mf is None:
            return
        self._map_load_overlay = QFrame(mf)
        self._map_load_overlay.setObjectName("mapLoadOverlay")
        lay = QVBoxLayout(self._map_load_overlay)
        lay.setContentsMargins(24, 24, 24, 24)
        self.lbl_map_load_title = QLabel("Loading offline map…")
        self.lbl_map_load_title.setObjectName("mapLoadTitle")
        self.lbl_map_load_title.setAlignment(Qt.AlignCenter)
        self.lbl_map_load_detail = QLabel("")
        self.lbl_map_load_detail.setObjectName("mapLoadDetail")
        self.lbl_map_load_detail.setAlignment(Qt.AlignCenter)
        self.lbl_map_load_detail.setWordWrap(True)
        lay.addStretch(1)
        lay.addWidget(self.lbl_map_load_title)
        lay.addSpacing(8)
        lay.addWidget(self.lbl_map_load_detail)
        lay.addStretch(1)
        self._map_load_seconds = 0
        self._map_load_timer = QTimer(self)
        self._map_load_timer.timeout.connect(self._tick_map_load_overlay)
        self._sync_map_load_overlay_geometry()

    def _sync_map_load_overlay_geometry(self) -> None:
        if not hasattr(self, "_map_load_overlay"):
            return
        mf = getattr(self, "_map_frame", None)
        if mf is not None:
            self._map_load_overlay.setGeometry(mf.rect())

    def _show_map_load_overlay(self) -> None:
        if not hasattr(self, "_map_load_overlay"):
            return
        if getattr(self, "_map_js_ready", False):
            return
        self._map_load_seconds = 0
        self._tick_map_load_overlay()
        self._sync_map_load_overlay_geometry()
        self._map_load_overlay.show()
        self._map_load_overlay.raise_()
        self._map_load_timer.start(1000)

    def _tick_map_load_overlay(self) -> None:
        if not hasattr(self, "lbl_map_load_detail"):
            return
        self._map_load_seconds += 1
        if getattr(self, "_work_laptop", False):
            self.lbl_map_load_detail.setText(
                "First open on a 4 GB work laptop can take 3–5 minutes.\n"
                "Stay plugged in and leave this window open.\n\n"
                f"Elapsed: {self._map_load_seconds}s")
        else:
            self.lbl_map_load_detail.setText(f"Elapsed: {self._map_load_seconds}s")

    def _hide_map_load_overlay(self) -> None:
        if hasattr(self, "_map_load_timer"):
            self._map_load_timer.stop()
        if hasattr(self, "_map_load_overlay"):
            self._map_load_overlay.hide()

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        side = QWidget()
        side.setObjectName("sidepanel")
        side.setMinimumWidth(SIDE_MIN)
        side.setMaximumWidth(SIDE_MAX)
        side.setAutoFillBackground(True)
        side.setAttribute(Qt.WA_StyledBackground, True)
        self._side_panel = side
        side_lay = QHBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.setSpacing(0)

        nav = QWidget()
        nav.setObjectName("navRail")
        nav.setFixedWidth(NAV_WIDTH)
        nav_lay = QVBoxLayout(nav)
        nav_lay.setContentsMargins(NAV_PAD_H, NAV_PAD_V, NAV_PAD_H, NAV_PAD_V)
        nav_lay.setSpacing(NAV_GAP)
        self._nav_labels = ("Setup", "Route", "Install", "Pickup", "Audit", "Fleet")
        for idx, label in enumerate(self._nav_labels):
            b = QPushButton(label)
            b.setObjectName("navBtn")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, i=idx: self._go_page(i))
            nav_lay.addWidget(b)
            setattr(self, f"_navbtn_{idx}", b)
        self._navbtn_0.setChecked(True)
        nav_lay.addStretch(1)
        side_lay.addWidget(nav)

        pages_col = QWidget()
        pages_col.setObjectName("pagesColumn")
        pages_col.setMinimumWidth(340 if getattr(self, "_work_laptop", False) else 300)
        pages_lay = QVBoxLayout(pages_col)
        pages_lay.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._page_shell(setup_page.build_setup_page(self)))   # 0
        self.pages.addWidget(self._page_shell(route_page.build_route_page(self)))   # 1
        self.pages.addWidget(self._page_shell(install_page.build_install_page(self)))  # 2
        self.pages.addWidget(self._page_shell(pickup_page.build_pickup_page(self)))     # 3
        self.pages.addWidget(self._page_shell(audit_page.build_audit_page(self)))      # 4
        self.pages.addWidget(self._page_shell(inventory_page.build_inventory_page(self)))  # 5
        pages_lay.addWidget(self.pages)
        side_lay.addWidget(pages_col, 1)

        map_frame = QFrame()
        map_frame.setObjectName("mapFrame")
        map_frame.setFrameShape(QFrame.NoFrame)
        map_frame.setAutoFillBackground(True)
        map_frame.setAttribute(Qt.WA_StyledBackground, True)
        map_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        map_lay = QVBoxLayout(map_frame)
        map_lay.setContentsMargins(0, 0, 0, 0)
        map_lay.setSpacing(0)
        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(self._placeholder())  # 0
        self.view.setParent(None)
        self.right_stack.addWidget(self.view)            # 1
        map_lay.addWidget(self.right_stack)
        self._map_frame = map_frame

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setObjectName("mainSplit")
        self._splitter.setChildrenCollapsible(False)
        self._splitter.addWidget(side)
        self._splitter.addWidget(map_frame)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes(list(SPLIT_DEFAULT))
        body.addWidget(self._splitter, 1)

        wrap = QWidget()
        wrap.setLayout(body)
        root.addWidget(wrap, 1)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())
        self.status_gps = QLabel("GPS: searching...")
        self.status_power = QLabel("")
        self.status_route = QLabel("")
        self.statusBar().addWidget(self.status_gps)
        self.statusBar().addPermanentWidget(self.status_power)
        self.statusBar().addPermanentWidget(self.status_route)
        self._refresh_origin_label()
        self._refresh_workflow_strip()
        self._update_right()
        if hasattr(self, "lbl_pick_status"):
            self._refresh_route_pick_ui()

    def _sync_prefs_ui(self) -> None:
        """No voice/theme prefs on route page after voice removal."""
        return

    def _page_shell(self, w: QWidget) -> QWidget:
        """Scrollable tab body — prevents overlap when panel height is tight."""
        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        w.setMinimumWidth(300)
        scroll.setWidget(w)
        return scroll

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_side_panel"):
            self._side_panel.raise_()
        self._sync_map_load_overlay_geometry()

    def _placeholder(self) -> QWidget:
        w = QWidget()
        w.setObjectName("placeholder")
        v = QVBoxLayout(w)
        v.setContentsMargins(48, 48, 48, 48)
        v.addStretch(1)
        t = QLabel(APP_NAME)
        t.setObjectName("phTitle")
        t.setAlignment(Qt.AlignCenter)
        sub = QLabel(APP_TAGLINE)
        sub.setObjectName("phSub")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        v.addWidget(t)
        v.addSpacing(6)
        v.addWidget(sub)
        v.addSpacing(24)
        for text in (
            "1  Set your start (GPS, address, or coordinates)",
            "2  Add Excel + .EST, download road map",
            "3  Build optimized route — map appears here",
        ):
            step = QLabel(text)
            step.setObjectName("phStep")
            step.setAlignment(Qt.AlignCenter)
            v.addWidget(step)
            v.addSpacing(8)
        v.addStretch(1)
        return w
