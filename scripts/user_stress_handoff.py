"""User stress test — shipped AppUpdate folder, work-laptop mode.

Exercises the exact handoff layout (dist/TrafficDeployer-AppUpdate/TrafficDeployer)
as OPEN_APP.bat would: TDS_WORK_LAPTOP=1, tds_data beside exe, frozen web assets.

Logs: logs/handoff_stress/YYYY-MM-DD.jsonl

Override: TD_HANDOFF=C:\\path\\to\\TrafficDeployer
Job files: TD_JOB_XLS + TD_JOB_EST (see field_job_fixtures.py); bundled demo if unset.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from field_job_fixtures import resolve_field_job  # noqa: E402
HANDOFF_DEFAULT = os.path.join(ROOT, "dist", "TrafficDeployer-AppUpdate", "TrafficDeployer")
LOG_DIR = os.path.join(ROOT, "logs", "handoff_stress")
REPO_DATA = os.path.join(ROOT, "tds_data")

# Work-laptop UX budgets (seconds)
NAV_WARN_S = 4.0
NAV_FAIL_S = 7.0  # WebEngine cold start often 4–6s post-reboot; hangs are >>7s
MAP_WARN_S = 120.0
MAP_FAIL_S = 300.0
CLICK_FAIL_S = 5.0
EXE_START_WARN_S = 45.0
EXE_START_FAIL_S = 120.0

FAILURES: list[str] = []
WARNS: list[str] = []
SCENARIOS: list[dict] = []


def _handoff() -> str:
    return os.environ.get("TD_HANDOFF", "").strip() or HANDOFF_DEFAULT


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"  FAIL {msg}")


def warn(msg: str) -> None:
    WARNS.append(msg)
    print(f"  WARN {msg}")


def ok(msg: str, detail: str = "") -> None:
    line = f"  OK  {msg}" + (f" — {detail}" if detail else "")
    print(line, flush=True)


def section(title: str) -> None:
    print(f"\n[{title}]")


def _record(name: str, seconds: float, *, ok_flag: bool = True, detail: str = "") -> None:
    SCENARIOS.append({
        "name": name,
        "seconds": round(seconds, 3),
        "ok": ok_flag,
        "detail": detail,
        "ts": datetime.now(timezone.utc).isoformat(),
    })


def _ensure_handoff_data(handoff: str) -> None:
    """AppUpdate has no map — mirror laptop: keep tds_data, link map + graph for test."""
    data = os.path.join(handoff, "tds_data")
    os.makedirs(os.path.join(data, "counter_downloads"), exist_ok=True)
    os.makedirs(os.path.join(data, "crashes"), exist_ok=True)
    for name in ("california.pmtiles", "road_graph.graphml"):
        src = os.path.join(REPO_DATA, name)
        dst = os.path.join(data, name)
        if not os.path.isfile(src):
            fail(f"build PC missing {name} — cannot simulate laptop map")
            continue
        if os.path.isfile(dst):
            ok(f"handoff {name}", "already present")
            continue
        try:
            os.link(src, dst)
            ok(f"handoff {name}", "hard-linked from repo tds_data")
        except OSError:
            shutil.copy2(src, dst)
            ok(f"handoff {name}", "copied from repo tds_data")


def _patch_paths_for_handoff(handoff: str) -> None:
    import ui.paths as paths

    paths.APP_DIR = handoff
    paths.IS_PORTABLE = True
    paths.LAUNCH_HINT = "Double-click OPEN_APP.bat"
    paths.WEB_DIR = paths._resolve_web_dir(handoff)
    paths.DEMO_DIR = paths._resolve_demo_dir(handoff, paths.WEB_DIR)
    paths.DATA_DIR = os.path.join(handoff, "tds_data")
    paths.COUNTER_DOWNLOAD_DIR = os.path.join(paths.DATA_DIR, "counter_downloads")
    paths.CRASH_DIR = os.path.join(paths.DATA_DIR, "crashes")
    paths.VENDOR_DIR = os.path.join(paths.DATA_DIR, "vendor")
    paths.DEMO_CSV = os.path.join(paths.DEMO_DIR, "demo_sites.csv")
    paths.DEMO_EST = os.path.join(paths.DEMO_DIR, "DemoDay.EST")
    for d in (paths.DATA_DIR, paths.COUNTER_DOWNLOAD_DIR, paths.CRASH_DIR, paths.VENDOR_DIR):
        os.makedirs(d, exist_ok=True)


def _find_window_title(sub: str, timeout_s: float) -> bool:
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        user32 = ctypes.windll.user32
        found = False
        deadline = time.perf_counter() + timeout_s

        def _enum(hwnd, _):
            nonlocal found
            if not user32.IsWindowVisible(hwnd):
                return True
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            if sub.lower() in (buf.value or "").lower():
                found = True
                return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        cb = WNDENUMPROC(_enum)
        while time.perf_counter() < deadline and not found:
            user32.EnumWindows(cb, 0)
            time.sleep(0.25)
        return found
    except Exception as exc:  # noqa: BLE001
        warn(f"window probe skipped: {exc}")
        return True


def test_frozen_exe_startup(handoff: str) -> None:
    section("1. Frozen exe cold start (subprocess)")
    exe = os.path.join(handoff, "TrafficDeployer.exe")
    if not os.path.isfile(exe):
        fail("TrafficDeployer.exe missing")
        return
    env = {**os.environ, "TDS_WORK_LAPTOP": "1"}
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        [exe],
        cwd=handoff,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    appeared = _find_window_title("Traffic Deployer", EXE_START_FAIL_S)
    elapsed = time.perf_counter() - t0
    _record("frozen_exe_window", elapsed, ok_flag=appeared, detail=f"pid={proc.pid}")
    if not appeared:
        fail(f"exe window not visible within {EXE_START_FAIL_S:.0f}s")
    elif elapsed > EXE_START_FAIL_S:
        fail(f"exe startup {elapsed:.1f}s (>{EXE_START_FAIL_S:.0f}s)")
    elif elapsed > EXE_START_WARN_S:
        warn(f"exe startup slow {elapsed:.1f}s — laptop may feel stuck on first open")
        ok("exe window appeared", f"{elapsed:.1f}s")
    else:
        ok("exe window appeared", f"{elapsed:.1f}s")
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def _pump(app, ms: int = 50) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _wait_js_flag(app, win, flag: str, timeout_s: float) -> tuple[bool, float]:
    """Poll window.<flag> via runJavaScript (same as in-app map health)."""
    from PySide6.QtCore import QTimer

    result = {"v": None}
    t0 = time.perf_counter()

    def poll() -> None:
        if time.perf_counter() - t0 >= timeout_s:
            result["v"] = False
            return

        def cb(val) -> None:
            if val:
                result["v"] = True
            elif time.perf_counter() - t0 < timeout_s:
                QTimer.singleShot(200, poll)
            else:
                result["v"] = False

        win.view.page().runJavaScript(f"!!window.{flag}", cb)

    poll()
    while result["v"] is None and time.perf_counter() - t0 < timeout_s:
        app.processEvents()
        _pump(app, 50)
    elapsed = time.perf_counter() - t0
    return bool(result["v"]), elapsed


def test_ui_stress(handoff: str) -> None:
    section("2. UI stress (handoff paths + work-laptop mode)")
    os.environ["TDS_WORK_LAPTOP"] = "1"
    sys.frozen = True  # type: ignore[attr-defined]
    sys.executable = os.path.join(handoff, "TrafficDeployer.exe")
    sys._MEIPASS = os.path.join(handoff, "_internal")  # type: ignore[attr-defined]

    from core.hardware_profile import apply_webengine_env

    apply_webengine_env()

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QPushButton

    _patch_paths_for_handoff(handoff)
    web_ok, web_msg = __import__("ui.paths", fromlist=["web_assets_ok"]).web_assets_ok()
    if not web_ok:
        fail(f"web assets: {web_msg}")
        return
    ok("web assets", web_msg)

    app = QApplication.instance() or QApplication(sys.argv)
    from main import MainWindow

    t0 = time.perf_counter()
    win = MainWindow()
    win.show()
    app.processEvents()
    init_s = time.perf_counter() - t0
    _record("mainwindow_init", init_s)
    if init_s > NAV_FAIL_S:
        fail(f"MainWindow init {init_s:.1f}s")
    elif init_s > NAV_WARN_S:
        warn(f"MainWindow init slow {init_s:.1f}s")
    else:
        ok("MainWindow init", f"{init_s:.2f}s")

    map_ready = {"v": False}
    win.bridge.mapReady.connect(lambda: map_ready.__setitem__("v", True))
    print("  ... waiting for map (work-laptop may take 3–5 min)", flush=True)
    # Gate on tiles (__mapLoaded), not QWebChannel — map can render without bridge.
    loaded, map_s = _wait_js_flag(app, win, "__mapLoaded", MAP_FAIL_S)
    _record("map_loaded", map_s, ok_flag=loaded)
    if not loaded:
        fail(f"map tiles never loaded ({map_s:.0f}s) — check california.pmtiles beside exe")
    elif map_s > MAP_WARN_S:
        warn(f"map load slow {map_s:.0f}s — matches 3–5 min laptop warning")
        ok("map loaded", f"{map_s:.1f}s")
    else:
        ok("map loaded", f"{map_s:.1f}s")
    bridge_ok, bridge_s = _wait_js_flag(app, win, "__bridgeReady", 30.0)
    _record("bridge_ready", bridge_s, ok_flag=bridge_ok)
    if bridge_ok:
        ok("JS bridge", f"{bridge_s:.1f}s")
    else:
        warn(f"JS bridge not ready in {bridge_s:.0f}s — clicks use tdstop:// fallback")

    section("3. Rapid nav switching")
    for round_i in range(3):
        for page in range(5):
            t0 = time.perf_counter()
            win._go_page(page)
            app.processEvents()
            elapsed = time.perf_counter() - t0
            _record(f"nav_{page}_r{round_i}", elapsed, ok_flag=elapsed < NAV_FAIL_S)
            if elapsed > NAV_FAIL_S:
                fail(f"nav page {page} froze {elapsed:.1f}s (round {round_i})")
            elif elapsed > NAV_WARN_S:
                warn(f"nav page {page} slow {elapsed:.2f}s (round {round_i})")
    ok("nav stress", "15 page switches")

    section("4. Button clicks per page (safe subset)")
    slow_clicks: list[str] = []
    dead_clicks: list[str] = []
    skip_words = (
        "about", "smoke", "wizard", "checklist", "download", "import",
        "offline", "online", "update", "undo", "clear counter", "read serial",
        "build route", "pick route", "apply", "export", "save profile",
    )
    for page in range(5):
        win._go_page(page)
        app.processEvents()
        _pump(app, 100)
        buttons = [
            b for b in win.findChildren(QPushButton)
            if b.isVisible() and b.isEnabled() and b.text().strip()
        ]
        clicked = 0
        for btn in buttons:
            label = btn.text().strip().replace("\n", " ")[:40]
            low = label.lower()
            if any(w in low for w in skip_words):
                continue
            if clicked >= 4:
                break
            t0 = time.perf_counter()
            try:
                QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
            except RuntimeError:
                dead_clicks.append(f"p{page}:{label}")
                continue
            for _ in range(8):
                app.processEvents()
                _pump(app, 80)
            elapsed = time.perf_counter() - t0
            clicked += 1
            _record(f"click_p{page}", elapsed, ok_flag=elapsed < CLICK_FAIL_S, detail=label)
            if elapsed >= CLICK_FAIL_S:
                slow_clicks.append(f"p{page}:{label} ({elapsed:.1f}s)")
    if dead_clicks:
        warn("buttons destroyed mid-click: " + ", ".join(dead_clicks[:5]))
    if slow_clicks:
        for s in slow_clicks[:8]:
            fail(f"click hang: {s}")
    else:
        ok("button clicks", "no >5s hangs on visible buttons")

    section("5. Workflow actions")
    job = resolve_field_job()
    job_xls_ok = os.path.isfile(job.xls)
    job_ests = [(p, lbl) for p, lbl in job.ests if os.path.isfile(p)]
    if job_xls_ok and job_ests:
        win._go_page(0)
        win.excel_paths = [job.xls]
        win.est_paths = [p for p, _ in job_ests]
        win.state.excel_paths = list(win.excel_paths)
        win.state.est_paths = list(win.est_paths)
        if hasattr(win.state, "set_start_point"):
            try:
                win.state.set_start_point(job.home[0], job.home[1], job.home_label)
            except Exception:  # noqa: BLE001
                win.state.home = job.home
                win.state.default_home = job.home
        else:
            win.state.home = job.home
            win.state.default_home = job.home
        win._refresh_file_lists()
        app.processEvents()
        ok(
            "load job files",
            f"{job.label} ({job.source}): {os.path.basename(job.xls)} + "
            f"{len(job_ests)} est",
        )

        # Real field jobs can be large; keep headroom beyond demo 90s.
        build_budget = 300.0 if job.source != "bundled" else 90.0
        t0 = time.perf_counter()
        try:
            win._build_route_from_uploads()
            deadline = time.perf_counter() + build_budget
            while time.perf_counter() < deadline:
                app.processEvents()
                if getattr(win, "_route_pick_mode", False):
                    break
                rt = getattr(win, "_route_thread", None)
                if rt is None or not rt.isRunning():
                    break
                _pump(app, 100)
            # Drain queued finished_result slots after the worker exits.
            for _ in range(40):
                app.processEvents()
                _pump(app, 50)
            build_s = time.perf_counter() - t0
            still = getattr(win, "_route_thread", None)
            running = still is not None and still.isRunning()
            pick_mode = bool(getattr(win, "_route_pick_mode", False))
            miles = float((getattr(win.state, "route", None) or {}).get("miles") or 0)
            stops_n = len(getattr(win.state, "stops", None) or [])
            _record(
                "build_route",
                build_s,
                ok_flag=not running and pick_mode and stops_n > 0,
                detail=f"pick={pick_mode};miles={miles};stops={stops_n};job={job.label}",
            )
            if running:
                fail(f"BUILD ROUTE hung {build_s:.0f}s")
            elif not pick_mode:
                fail(f"BUILD ROUTE did not enter pick mode ({build_s:.0f}s)")
            elif stops_n <= 0:
                fail(f"BUILD ROUTE loaded 0 stops ({build_s:.0f}s)")
            elif build_s > 60:
                warn(f"BUILD ROUTE took {build_s:.0f}s — may feel stuck on laptop")
                ok("BUILD ROUTE", f"{build_s:.1f}s, pick mode, {stops_n} stops")
            else:
                ok("BUILD ROUTE", f"{build_s:.1f}s, pick mode, {stops_n} stops")
        except Exception as exc:  # noqa: BLE001
            fail(f"BUILD ROUTE: {exc}")
    else:
        missing = []
        if not job_xls_ok:
            missing.append(job.xls or "(no xls)")
        missing.extend(p for p, _ in job.ests if not os.path.isfile(p))
        warn(f"job files missing — skip BUILD ROUTE: {missing}")

    win._go_page(1)
    app.processEvents()
    t0 = time.perf_counter()
    try:
        win._show_route_pick_dialog()
        app.processEvents()
        _pump(app, 200)
        win._hide_route_pick_dialog()
        app.processEvents()
        pick_s = time.perf_counter() - t0
        _record("route_pick_dialog", pick_s)
        ok("route pick dialog open/close", f"{pick_s:.2f}s") if pick_s < NAV_FAIL_S else fail(
            f"route pick dialog slow {pick_s:.1f}s")
    except Exception as exc:  # noqa: BLE001
        fail(f"route pick dialog: {exc}")

    section("6. Map push under load")
    pushes = 0
    t0 = time.perf_counter()
    for _ in range(20):
        win._push_state()
        app.processEvents()
        pushes += 1
    push_s = time.perf_counter() - t0
    _record("map_push_x20", push_s)
    if push_s > 10:
        fail(f"20 map pushes took {push_s:.1f}s — map may lag in field")
    elif push_s > 4:
        warn(f"20 map pushes slow {push_s:.1f}s")
    else:
        ok("map push burst", f"{pushes} in {push_s:.2f}s")

    win.close()
    app.processEvents()
    _pump(app, 200)


def _write_log() -> str:
    os.makedirs(LOG_DIR, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(LOG_DIR, f"{day}.jsonl")
    row = {
        "handoff": _handoff(),
        "failures": FAILURES,
        "warnings": WARNS,
        "scenarios": SCENARIOS,
        "passed": not FAILURES,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return path


def main() -> int:
    handoff = _handoff()
    print("HANDOFF USER STRESS — shipped AppUpdate folder (work-laptop mode)")
    print(f"Target: {handoff}\n")

    if not os.path.isfile(os.path.join(handoff, "TrafficDeployer.exe")):
        print("FAIL — run BUILD_APP_UPDATE.bat first")
        return 1

    _ensure_handoff_data(handoff)
    test_ui_stress(handoff)
    test_frozen_exe_startup(handoff)

    log_path = _write_log()
    print("\n" + "=" * 60)
    print(f"FAIL: {len(FAILURES)}  WARN: {len(WARNS)}")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
        print(f"\nLog: {log_path}")
        print("HANDOFF STRESS FAIL — fix before laptop copy")
        return 1
    if WARNS:
        for w in WARNS:
            print(f"  ! {w}")
    print(f"\nLog: {log_path}")
    print("HANDOFF STRESS PASS — review warnings for laptop UX")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
