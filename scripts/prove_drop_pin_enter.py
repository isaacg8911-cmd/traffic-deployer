"""User-path proof: Drop pin mode must not freeze map or show corner pin before click."""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PROOF_DIR = os.path.join(ROOT, "logs", "manual_grab_proof")
PROOF_JSON = os.path.join(PROOF_DIR, "drop_pin_enter_proof.json")


def main() -> int:
    os.makedirs(PROOF_DIR, exist_ok=True)

    from scripts.open_week14_for_edit import build_week14_state

    st, focus_idx = build_week14_state(focus_site="15228")
    stop = st.stops[focus_idx]
    stop.pop("field_lat", None)
    stop.pop("field_lon", None)
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
        print(f"  {step}: {detail}" if detail is not None else f"  {step}")

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
        z0_holder: dict = {"z": None}

        def after_zoom_before(raw) -> None:
            try:
                z0_holder["z"] = json.loads(raw) if raw else {}
            except Exception as exc:  # noqa: BLE001
                z0_holder["z"] = {"err": str(exc), "raw": raw}
            log("zoom_before", z0_holder["z"])
            win._begin_manual_grab()
            log("manual_grab_on", win._manual_grab_mode)
            QTimer.singleShot(600, check_after_enter)

        win.view.page().runJavaScript(
            "(function(){return JSON.stringify({"
            "zoom: window._map && window._map.getZoom(),"
            "pin: window.__tdLastPinDrop || null,"
            "marker: !!(window._map && document.querySelector('.maplibregl-marker')),"
            "manual: !!(window.__tdSetManualGrab)"
            "});})()",
            after_zoom_before,
        )

        def check_after_enter() -> None:
            js = (
                "(function(){"
                "if (window._map) { window._map.zoomTo(14, {duration:0}); }"
                "var z1 = window._map ? window._map.getZoom() : null;"
                "window._map && window._map.zoomTo(Math.min((z1||12)+1,18), {duration:0});"
                "var z2 = window._map ? window._map.getZoom() : null;"
                "return JSON.stringify({"
                "pin: window.__tdLastPinDrop || null,"
                "markerCount: document.querySelectorAll('.maplibregl-marker').length,"
                "zoomBefore: z1, zoomAfter: z2,"
                "banner: (document.getElementById('pick-banner')||{}).textContent || '',"
                "manualForced: !!window.__tdSetManualGrab"
                "});"
                "})()"
            )

            def after_check(raw) -> None:
                try:
                    info = json.loads(raw) if raw else {}
                except Exception as exc:  # noqa: BLE001
                    info = {"parse_err": str(exc), "raw": raw}
                log("after_enter", info)
                pin = info.get("pin")
                bad_pin = pin is not None and (
                    abs(float(pin.get("lat", 0))) < 1 or abs(float(pin.get("lon", 0))) < 1
                )
                marker_before_click = pin is not None
                zoom_ok = (
                    info.get("zoomBefore") is not None
                    and info.get("zoomAfter") is not None
                    and float(info["zoomAfter"]) > float(info["zoomBefore"])
                )
                banner_ok = "Drop pin" in str(info.get("banner") or "")
                ok = (not bad_pin) and (not marker_before_click) and zoom_ok and banner_ok
                proof["checks"] = {
                    "no_corner_pin": not bad_pin,
                    "no_marker_before_click": not marker_before_click,
                    "zoom_works": zoom_ok,
                    "banner_ok": banner_ok,
                }
                finish(ok, "drop pin enter keeps map responsive" if ok else str(proof["checks"]))

            win.view.page().runJavaScript(js, after_check)

    polls = {"n": 0}

    def poll() -> None:
        polls["n"] += 1
        if win._map_js_ready:
            QTimer.singleShot(400, run_when_ready)
            return
        if polls["n"] > 200:
            finish(False, "map never became ready")
            return
        QTimer.singleShot(200, poll)

    QTimer.singleShot(500, poll)
    app.exec()
    return 0 if proof.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
