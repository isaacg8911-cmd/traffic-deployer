"""Launch app, INSTALL site without GPS/counter clear — user-path proof."""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PROOF_DIR = os.path.join(ROOT, "logs", "manual_grab_proof")
PROOF_JSON = os.path.join(PROOF_DIR, "install_no_block_proof.json")


def main() -> int:
    os.makedirs(PROOF_DIR, exist_ok=True)

    from scripts.open_week14_for_edit import build_week14_state

    st, focus_idx = build_week14_state(focus_site="15228")
    stop = st.stops[focus_idx]
    stop.pop("field_lat", None)
    stop.pop("field_lon", None)
    stop.pop("counter_cleared_at", None)
    stop.pop("installed", None)
    stop.pop("skipped", None)
    stop.pop("serial", None)
    stop.pop("counter_serial", None)
    st.current_index = focus_idx
    st.save()

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from main import MainWindow
    from scripts.proof_contracts import split_mainwindow_contract

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()
    proof: dict = {"steps": [], "pass": False}
    proof["architecture"] = split_mainwindow_contract(win)

    def log(step: str, detail: object = None) -> None:
        entry = {"t": round(time.time(), 3), "step": step}
        if detail is not None:
            entry["detail"] = detail
        proof["steps"].append(entry)
        text = f"  {step}" + (f"  {detail}" if detail is not None else "")
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("ascii", errors="replace").decode("ascii"))

    def finish(ok: bool, msg: str) -> None:
        proof["pass"] = ok
        proof["message"] = msg
        with open(PROOF_JSON, "w", encoding="utf-8") as f:
            json.dump(proof, f, indent=2)
        print(f"\n{'OK' if ok else 'FAIL'}  {msg}")
        print(f"    proof  {PROOF_JSON}")
        QTimer.singleShot(300, app.quit)

    def run_when_ready() -> None:
        if not win._map_js_ready:
            return
        log("map_ready", True)
        win._go_page(2)
        win.current_index = focus_idx
        win._refresh_install()
        items_before = win.lbl_install_checklist.text()
        log("checklist", items_before)

        win._commit_install(True)
        s = win.state.stops[focus_idx]
        installed = bool(s.get("installed"))
        no_gps = s.get("field_lat") is None
        no_clear = not str(s.get("counter_cleared_at") or "").strip()
        log("after_install", {
            "installed": installed,
            "no_gps": no_gps,
            "no_clear": no_clear,
            "site_id": s.get("id"),
        })
        ok = installed and no_gps and no_clear
        finish(ok, f"INSTALL without GPS/clear for site {s.get('id')}")

    polls = {"n": 0}

    def poll() -> None:
        polls["n"] += 1
        if win._map_js_ready:
            QTimer.singleShot(300, run_when_ready)
            return
        if polls["n"] > 200:
            finish(False, "map never became ready")
            return
        QTimer.singleShot(200, poll)

    QTimer.singleShot(500, poll)
    exit_code = app.exec()
    return 0 if proof.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
