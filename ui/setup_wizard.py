"""Three-step home setup wizard (start → files → road & build)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


from ui.simple_mode import BUILD_LABEL


class SetupWizard(QDialog):
    """Guides through origin, uploads, and first route build."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self._win = main_window
        self.setWindowTitle("Quick setup — 3 steps")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        self._stack = QStackedWidget()
        lay.addWidget(self._stack, 1)
        self._stack.addWidget(self._page_start())
        self._stack.addWidget(self._page_files())
        self._stack.addWidget(self._page_build())
        nav = QHBoxLayout()
        self._lbl_step = QLabel("Step 1 of 3")
        nav.addWidget(self._lbl_step)
        nav.addStretch(1)
        self._btn_back = QPushButton("Back")
        self._btn_back.clicked.connect(self._back)
        self._btn_next = QPushButton("Next")
        self._btn_next.setObjectName("primary")
        self._btn_next.clicked.connect(self._next)
        nav.addWidget(self._btn_back)
        nav.addWidget(self._btn_next)
        lay.addLayout(nav)
        self._update_nav()

    def _page_start(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(
            "<b>Step 1 — Starting point</b><br>"
            "Set where you leave from and return to. Use GPS, address search, or coordinates."
        ))
        v.addWidget(QLabel(
            f"Current: {self._win.state.home[0]:.5f}, {self._win.state.home[1]:.5f}"
        ))
        b_gps = QPushButton("Read USB GPS")
        b_gps.clicked.connect(self._win._origin_from_gps)
        v.addWidget(b_gps)
        b_addr = QPushButton("Search address (online)")
        b_addr.clicked.connect(self._win._origin_from_address)
        v.addWidget(b_addr)
        b_save = QPushButton("Save coordinates from Setup spinboxes")
        b_save.clicked.connect(self._win._origin_from_coords)
        v.addWidget(b_save)
        b_def = QPushButton("Save as DEFAULT start")
        b_def.clicked.connect(self._win._save_default_home)
        v.addWidget(b_def)
        v.addStretch(1)
        return w

    def _page_files(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(
            "<b>Step 2 — Field files</b><br>"
            "Add Excel/CSV site list and matching .EST map file(s)."
        ))
        ex = len(self._win.excel_paths)
        es = len(self._win.est_paths)
        v.addWidget(QLabel(f"Excel: {ex} file(s) · EST: {es} file(s)"))
        b_ex = QPushButton("Add Excel / CSV")
        b_ex.clicked.connect(self._win._pick_excel)
        v.addWidget(b_ex)
        b_est = QPushButton("Add .EST map(s)")
        b_est.clicked.connect(self._win._pick_est)
        v.addWidget(b_est)
        b_demo = QPushButton("Load demo files")
        b_demo.clicked.connect(self._win._load_demo_files)
        v.addWidget(b_demo)
        v.addStretch(1)
        return w

    def _page_build(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        import road_router
        from ui.paths import DATA_DIR

        has_g = road_router.has_graph(DATA_DIR)
        v.addWidget(QLabel(
            "<b>Step 3 — Road map & route</b><br>"
            "Download or import the offline road graph, then build the optimized route."
        ))
        v.addWidget(QLabel("Road map: " + ("saved locally" if has_g else "not downloaded yet")))
        b_dl = QPushButton("Download road map (online)")
        b_dl.clicked.connect(self._win._download_roads)
        v.addWidget(b_dl)
        b_imp = QPushButton("Import road map (.graphml)")
        b_imp.clicked.connect(self._win._import_roads)
        v.addWidget(b_imp)
        b_build = QPushButton(BUILD_LABEL)
        b_build.setObjectName("primary")
        b_build.clicked.connect(self._finish_build)
        v.addWidget(b_build)
        b_ck = QPushButton("Setup checklist")
        b_ck.clicked.connect(self._win._show_setup_checklist)
        v.addWidget(b_ck)
        v.addStretch(1)
        return w

    def _finish_build(self):
        self._win._build_route_from_uploads()
        self.accept()

    def _back(self):
        i = self._stack.currentIndex()
        if i > 0:
            self._stack.setCurrentIndex(i - 1)
            self._update_nav()

    def _next(self):
        i = self._stack.currentIndex()
        if i < self._stack.count() - 1:
            self._stack.setCurrentIndex(i + 1)
            self._update_nav()
        else:
            self.accept()

    def _update_nav(self):
        i = self._stack.currentIndex()
        n = self._stack.count()
        self._lbl_step.setText(f"Step {i + 1} of {n}")
        self._btn_back.setEnabled(i > 0)
        self._btn_next.setText("Done" if i == n - 1 else "Next")
