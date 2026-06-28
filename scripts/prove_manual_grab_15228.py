"""Launch app, manual-grab site 15228 at begin/end midpoint — proof artifact."""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SITE_ID = "15228"
PROOF_DIR = os.path.join(ROOT, "logs", "manual_grab_proof")
PROOF_JSON = os.path.join(PROOF_DIR, f"{SITE_ID}_proof.json")
PROOF_PNG = os.path.join(PROOF_DIR, f"{SITE_ID}_after.png")


def midpoint(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def stop_segment(stop: dict) -> tuple[tuple[float, float], tuple[float, float]] | None:
    b_lat, b_lon = stop.get("begin_lat"), stop.get("begin_lon")
    e_lat, e_lon = stop.get("end_lat"), stop.get("end_lon")
    if None in (b_lat, b_lon, e_lat, e_lon):
        return None
    return (float(b_lat), float(b_lon)), (float(e_lat), float(e_lon))


def find_stop(stops: list[dict], site_id: str) -> tuple[int, dict] | None:
    for i, s in enumerate(stops):
        if str(s.get("id")) == site_id:
            return i, s
    return None


def main() -> int:
    os.makedirs(PROOF_DIR, exist_ok=True)

    from scripts.open_week14_for_edit import build_week14_state

    st, focus_idx = build_week14_state(focus_site=SITE_ID)
    found = find_stop(st.stops, SITE_ID)
    if not found:
        print(f"FAIL site {SITE_ID} not in Week 14 stops")
        return 1
    idx, stop = found
    seg = stop_segment(stop)
    if not seg:
        print(f"FAIL site {SITE_ID} missing begin/end segment coords")
        return 1

    begin, end = seg
    mid = midpoint(begin, end)
    # Clear prior field GPS so proof is unambiguous.
    stop.pop("field_lat", None)
    stop.pop("field_lon", None)
    stop.pop("field_coord_source", None)
    st.current_index = idx
    st.save()

    before = {
        "site_id": SITE_ID,
        "stop_index": idx + 1,
        "begin": {"lat": begin[0], "lon": begin[1]},
        "end": {"lat": end[0], "lon": end[1]},
        "target_midpoint": {"lat": mid[0], "lon": mid[1]},
        "field_lat_before": stop.get("field_lat"),
    }

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from main import MainWindow
    from scripts.proof_contracts import split_mainwindow_contract

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()
    proof: dict = {"before": before, "steps": [], "pass": False}
    proof["architecture"] = split_mainwindow_contract(win)

    def log(step: str, detail: object = None) -> None:
        entry = {"t": round(time.time(), 3), "step": step}
        if detail is not None:
            entry["detail"] = detail
        proof["steps"].append(entry)
        print(f"  {step}" + (f"  {detail}" if detail is not None else ""))

    def fail(msg: str) -> None:
        log("FAIL", msg)
        proof["error"] = msg
        _write_proof(proof)
        app.quit()

    def _write_proof(data: dict) -> None:
        with open(PROOF_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def run_grab_when_ready() -> None:
        if not win._map_js_ready:
            return
        log("map_ready", True)

        win._go_page(2)
        win.current_index = idx
        win._begin_manual_grab()
        log("manual_grab_on", win._manual_grab_mode)

        pin_holder: dict = {"done": False, "pin": None, "err": None}

        def after_pin_drop(_raw) -> None:
            read_pin_js = (
                "JSON.stringify({ok:true,pin:window.__tdLastPinDrop||null,"
                "hook:typeof window.__tdShowDropPinOnly})"
            )

            def after_pin_read(raw) -> None:
                try:
                    import json as _json

                    pin_parsed = _json.loads(raw) if raw else {"ok": False, "err": "empty_pin_read"}
                except Exception as exc:  # noqa: BLE001
                    pin_parsed = {"ok": False, "err": str(exc), "raw": raw}
                pin_holder["pin"] = pin_parsed.get("pin")
                log("pin_drop", pin_parsed)

                win.bridge.onMapClick(mid[0], mid[1])
                log("bridge_onMapClick", {"lat": mid[0], "lon": mid[1]})
                pin_holder["done"] = True
                finish_grab_proof()

            win.view.page().runJavaScript(read_pin_js, after_pin_read)

        def finish_grab_proof() -> None:
            if not pin_holder["done"]:
                return
            _assert_grab_saved()

        def _assert_grab_saved() -> None:
            saved = win.state.stops[idx]
            got_lat = saved.get("field_lat")
            got_lon = saved.get("field_lon")
            tol = 1e-4
            ok_lat = got_lat is not None and abs(float(got_lat) - mid[0]) < tol
            ok_lon = got_lon is not None and abs(float(got_lon) - mid[1]) < tol
            ok_src = saved.get("field_coord_source") == "manual"
            pin = pin_holder.get("pin") or {}
            ok_pin = (
                pin.get("lat") is not None
                and pin.get("lon") is not None
                and abs(float(pin["lat"]) - mid[0]) < tol
                and abs(float(pin["lon"]) - mid[1]) < tol
            )
            lbl = win.lbl_grab.text() if hasattr(win, "lbl_grab") else ""
            ok_lbl = "Manual GPS" in lbl and f"{mid[0]:.5f}"[:7] in lbl

            proof["after"] = {
                "field_lat": got_lat,
                "field_lon": got_lon,
                "field_coord_source": saved.get("field_coord_source"),
                "lbl_grab": lbl,
                "pin_drop": pin,
                "backup_file": win.state.backup_file,
            }
            proof["pass"] = bool(ok_lat and ok_lon and ok_src and ok_pin and ok_lbl)
            proof["midpoint_match"] = bool(ok_lat and ok_lon and ok_src)
            proof["pin_drop_ok"] = ok_pin
            proof["sidebar_ok"] = ok_lbl

            try:
                pix = win.grab()
                pix.save(PROOF_PNG)
                proof["screenshot"] = PROOF_PNG
                log("screenshot", PROOF_PNG)
            except Exception as exc:  # noqa: BLE001
                log("screenshot_skip", str(exc))

            _write_proof(proof)

            if proof["pass"]:
                win._persist_shift(quiet=True)
                log("persist_shift", win.state.backup_file)
                print(f"\nOK  Manual grab saved for {SITE_ID} at segment midpoint")
                print(f"    begin  {begin[0]:.6f}, {begin[1]:.6f}")
                print(f"    end    {end[0]:.6f}, {end[1]:.6f}")
                print(f"    mid    {mid[0]:.6f}, {mid[1]:.6f}")
                print(f"    saved  {float(got_lat):.6f}, {float(got_lon):.6f}")
                print(f"    pin    {pin}")
                print(f"    lbl    {lbl}")
                print(f"    proof  {PROOF_JSON}")
                print(f"    png    {PROOF_PNG}")
            else:
                msg = (
                    f"coords={got_lat},{got_lon} pin={pin} lbl={lbl!r} "
                    f"ok_lat={ok_lat} ok_lon={ok_lon} ok_pin={ok_pin} ok_lbl={ok_lbl}"
                )
                print(f"\nFAIL manual grab pipeline: {msg}")
                fail(msg)

            QTimer.singleShot(800, app.quit)

        def after_grab_sync(_ready) -> None:
            verify_js = (
                "(function(){"
                "return JSON.stringify({"
                "manual: !!(window.__tdSetManualGrab),"
                "pinHook: typeof window.__tdShowDropPinOnly,"
                "loaded: !!window.__mapLoaded,"
                "map: !!window._map"
                "});"
                "})()"
            )

            def after_verify(raw) -> None:
                try:
                    import json as _json

                    info = _json.loads(raw) if raw else {}
                except Exception:  # noqa: BLE001
                    info = {"parse_err": raw}
                log("js_manual_grab_sync", info)
                drop_js = (
                    f"window.__tdShowDropPinOnly && window.__tdShowDropPinOnly({mid[0]}, {mid[1]}); true"
                )
                win.view.page().runJavaScript(drop_js, after_pin_drop)

            win.view.page().runJavaScript(verify_js, after_verify)

        win.view.page().runJavaScript(
            "window.__tdSetManualGrab && window.__tdSetManualGrab(true); true",
            after_grab_sync,
        )

    # Poll until map JS is ready (same as production startup).
    polls = {"n": 0}

    def poll() -> None:
        polls["n"] += 1
        if win._map_js_ready:
            QTimer.singleShot(400, run_grab_when_ready)
            return
        if polls["n"] > 200:
            fail("map never became ready")
            return
        QTimer.singleShot(200, poll)

    QTimer.singleShot(500, poll)
    exit_code = app.exec()
    return 0 if proof.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
