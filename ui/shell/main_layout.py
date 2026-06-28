"""Main window shell layout (nav rail, pages, map split) — P46 extract from main.py."""

from __future__ import annotations

from PySide6.QtCore import Qt
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

from ui.pages import audit_page, install_page, pickup_page, route_page, setup_page
from ui.simple_mode import FIELD_NAV_INDICES, FIELD_SHELL
from version import APP_NAME, APP_TAGLINE


class ShellLayoutMixin:
    def _apply_field_nav_shell(self) -> None:
        """Hide Setup/Audit in nav when offline field shell is active."""
        if not FIELD_SHELL:
            return
        on_field = bool(self.state.offline_mode)
        for i in range(5):
            btn = getattr(self, f"_navbtn_{i}", None)
            if btn is None:
                continue
            if on_field:
                btn.setVisible(i in FIELD_NAV_INDICES)
            else:
                btn.setVisible(True)
        if on_field and self.pages.currentIndex() not in FIELD_NAV_INDICES:
            self._go_page(1)

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
        side.setMinimumWidth(360)
        side.setMaximumWidth(440)
        side.setAutoFillBackground(True)
        side.setAttribute(Qt.WA_StyledBackground, True)
        self._side_panel = side
        side_lay = QHBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.setSpacing(0)

        nav = QWidget()
        nav.setObjectName("navRail")
        nav.setFixedWidth(64)
        nav_lay = QVBoxLayout(nav)
        nav_lay.setContentsMargins(6, 12, 6, 12)
        nav_lay.setSpacing(4)
        self._nav_labels = ("Setup", "Route", "Install", "Pickup", "Audit")
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
        pages_col.setMinimumWidth(320)
        pages_lay = QVBoxLayout(pages_col)
        pages_lay.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._wrap_scroll(setup_page.build_setup_page(self)))   # 0
        self.pages.addWidget(self._wrap_scroll(route_page.build_route_page(self)))   # 1
        self.pages.addWidget(self._wrap_scroll(install_page.build_install_page(self)))  # 2
        self.pages.addWidget(self._wrap_scroll(pickup_page.build_pickup_page(self)))     # 3
        self.pages.addWidget(self._wrap_scroll(audit_page.build_audit_page(self)))      # 4
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
        self._splitter.setSizes([400, 920])
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

    def _wrap_scroll(self, w: QWidget) -> QWidget:
        sc = QScrollArea()
        sc.setObjectName("pageScroll")
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setFrameShape(QFrame.NoFrame)
        w.setMinimumWidth(300)
        sc.setWidget(w)
        return sc

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_side_panel"):
            self._side_panel.raise_()

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
