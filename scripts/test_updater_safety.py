"""Updater failure modes: no relaunch loop, no downgrade, rollback, save before exit.

Covers ledger UPD-1..UPD-4. The helper .bat is executed for real in temp
folders with TD_APPLY_NO_LAUNCH set: success, copy failure, locked-file swap
failure, interrupted earlier run, and a launch through the real hidden-console
flags from a windowed (pythonw) parent.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import app_lifecycle  # noqa: E402
from core import auto_updater as au  # noqa: E402
from core import update_check  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, name: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {name}")
    if not cond:
        FAILS.append(name)


def _touch(path: str, text: str = "x") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _read(path: str) -> str:
    if not os.path.isfile(path):
        return "<missing>"
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().strip()


def _bundle(root: str, tag: str, *, internal: bool = True) -> None:
    _touch(os.path.join(root, "TrafficDeployer.exe"), f"exe-{tag}")
    _touch(os.path.join(root, "web", "index.html"), f"web-{tag}")
    if internal:
        _touch(os.path.join(root, "_internal", "lib.dll"), f"lib-{tag}")
        _touch(os.path.join(root, "_internal", "web", "index.html"), f"web-{tag}")


def _stage(root: str, tag: str) -> None:
    _bundle(root, tag)
    _touch(os.path.join(root, au.READY_COMPLETE), "ok")


def _state(data: str) -> dict:
    p = os.path.join(data, au.UPDATE_STATE_FILE)
    return json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else {}


def _set_state(data: str, **kw) -> None:
    s = _state(data)
    s.update(kw)
    au._write_state(data, s)


def _info(latest: str):
    return lambda cur: update_check.UpdateInfo(
        current=cur, latest=latest, update_available=True,
        download_url="http://example.invalid/u.zip", notes="")


class _Stub:
    """Swap module attributes for the duration of a test."""

    def __init__(self):
        self._saved: list[tuple[object, str, object]] = []

    def set(self, obj, name, value):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def restore(self):
        for obj, name, value in reversed(self._saved):
            setattr(obj, name, value)


def test_no_downgrade() -> None:
    print("[UPD-3 staged update older/equal is dropped]")
    with tempfile.TemporaryDirectory() as tmp:
        data = os.path.join(tmp, "tds_data")
        _stage(os.path.join(data, au.READY_DIRNAME), "old")
        _set_state(data, pending_apply="1.0.18")
        stub = _Stub()
        called = []
        stub.set(au, "schedule_apply_and_exit", lambda *a, **k: called.append(a))
        try:
            res = au.resume_pending_apply("1.0.19", app_dir=tmp, data_dir=data)
        finally:
            stub.restore()
        check(res is None and not called, "older staged update not applied")
        check(not os.path.isdir(os.path.join(data, au.READY_DIRNAME)), "older staged bundle removed")
        check(_state(data).get("last_failed_apply", {}).get("version") == "1.0.18", "reason recorded")

        _stage(os.path.join(data, au.READY_DIRNAME), "unknown")
        _set_state(data, pending_apply="")
        res = au.resume_pending_apply("1.0.19", app_dir=tmp, data_dir=data)
        check(res is None and not os.path.isdir(os.path.join(data, au.READY_DIRNAME)),
              "staged bundle with unknown version dropped")

    print("[staged copy that never finished is dropped, version stays downloadable]")
    with tempfile.TemporaryDirectory() as tmp:
        data = os.path.join(tmp, "tds_data")
        _bundle(os.path.join(data, au.READY_DIRNAME), "partial")
        _set_state(data, pending_apply="1.0.20")
        check(au.ready_bundle_path(data) is None, "partial copy is not offered as ready")
        res = au.resume_pending_apply("1.0.19", app_dir=tmp, data_dir=data)
        st = _state(data)
        check(res is None and not os.path.isdir(os.path.join(data, au.READY_DIRNAME)),
              "partial copy removed on launch")
        check("last_failed_apply" not in st and "pending_apply" not in st,
              "partial copy not recorded as a failed version")


def test_no_relaunch_loop() -> None:
    print("[UPD-1 failed apply does not close the app every launch]")
    with tempfile.TemporaryDirectory() as tmp:
        data = os.path.join(tmp, "tds_data")
        _stage(os.path.join(data, au.READY_DIRNAME), "new")
        _set_state(data, pending_apply="1.0.20")
        stub = _Stub()
        called = []
        stub.set(au, "schedule_apply_and_exit", lambda *a, **k: called.append(a))
        try:
            for _ in range(au.MAX_RESUME_ATTEMPTS):
                au.resume_pending_apply("1.0.19", app_dir=tmp, data_dir=data)
            check(len(called) == au.MAX_RESUME_ATTEMPTS, "retries up to the limit")
            res = au.resume_pending_apply("1.0.19", app_dir=tmp, data_dir=data)
        finally:
            stub.restore()
        check(len(called) == au.MAX_RESUME_ATTEMPTS, "no further exit after the limit")
        check(res is not None and not res.relaunch and bool(res.error), "gives up with a message")
        check(not os.path.isdir(os.path.join(data, au.READY_DIRNAME)), "staged bundle dropped")

    with tempfile.TemporaryDirectory() as tmp:
        data = os.path.join(tmp, "tds_data")
        _stage(os.path.join(data, au.READY_DIRNAME), "new")
        _set_state(data, pending_apply="1.0.20")
        _touch(os.path.join(data, au.FAILED_MARKER), "1.0.20")
        au._consume_failed_marker(data)
        check(not os.path.isdir(os.path.join(data, au.READY_DIRNAME)), "rolled-back marker drops bundle")
        check(not os.path.isfile(os.path.join(data, au.FAILED_MARKER)), "marker consumed")
        check("pending_apply" not in _state(data), "pending cleared")

        stub = _Stub()
        downloads = []
        stub.set(update_check, "check_for_update", _info("1.0.20"))
        stub.set(au, "_download", lambda *a, **k: downloads.append(a))
        try:
            res = au.check_and_apply("1.0.19", app_dir=tmp, data_dir=data,
                                     allow_apply=True, force_check=True)
        finally:
            stub.restore()
        check(not downloads and not res.relaunch and "failed to install" in res.error,
              "same failed version is not re-downloaded")


def test_save_before_exit() -> None:
    print("[UPD-4 in-app update saves the shift before exiting]")
    with tempfile.TemporaryDirectory() as tmp:
        data = os.path.join(tmp, "tds_data")
        bundle = os.path.join(tmp, "bundle")
        _bundle(bundle, "new")
        order: list[str] = []
        stub = _Stub()
        stub.set(au, "_launch_helper", lambda *a, **k: order.append("helper"))
        stub.set(au.sys, "exit", lambda code=0: order.append("exit"))
        try:
            try:
                au.schedule_apply_and_exit(bundle, tmp, data, "1.0.20",
                                           before_exit=lambda: order.append("save") or False)
                check(False, "failed save aborts update")
            except RuntimeError:
                check(order == ["save"], "failed save aborts update (no helper, no exit)")
            order.clear()
            au.schedule_apply_and_exit(bundle, tmp, data, "1.0.20",
                                       before_exit=lambda: order.append("save") or True)
            check(order == ["save", "helper", "exit"], "save runs before helper + exit")
        finally:
            stub.restore()

    with tempfile.TemporaryDirectory() as tmp:
        data = os.path.join(tmp, "tds_data")
        bundle = os.path.join(tmp, "bundle")
        _bundle(bundle, "new")
        downloads: list = []
        stub = _Stub()
        stub.set(update_check, "check_for_update", _info("1.0.21"))
        stub.set(au, "_download", lambda url, dest, **k: downloads.append(url))
        stub.set(au, "_extract_zip", lambda z, d: bundle)
        stub.set(au, "_launch_helper", lambda *a, **k: FAILS.append("helper ran after failed save"))
        try:
            res = au.check_and_apply("1.0.19", app_dir=tmp, data_dir=data, allow_apply=True,
                                     force_check=True, before_exit=lambda: False)
            check(not res.relaunch and not res.applied and "could not be saved" in res.error,
                  "caller is told not to relaunch when save fails")
            res2 = au.check_and_apply("1.0.19", app_dir=tmp, data_dir=data, allow_apply=True,
                                      force_check=True, before_exit=lambda: False)
            check(len(downloads) == 1 and "could not be saved" in res2.error,
                  "retry reuses the staged update (no second 300 MB download)")
        finally:
            stub.restore()

    print("[UPD-4 real shutdown routine]")
    from ui.controllers.setup import SetupControllerMixin
    from ui.shell.lifecycle import ShellLifecycleMixin

    class _Pages:
        def currentIndex(self):
            return 2

    class _Gps:
        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    class _Win(ShellLifecycleMixin):
        _save_before_update_exit = SetupControllerMixin._save_before_update_exit

        def __init__(self, save_ok: bool):
            self.save_ok = save_ok
            self.stopped: list[str] = []
            self.flushed = False
            self.pages = _Pages()
            self.gps = _Gps()
            for attr in ("_picocount_thread", "_route_thread", "_retrace_thread",
                         "_dl_thread", "_geocode_thread", "_field_street_thread"):
                setattr(self, attr, attr)
            self._field_street_threads = ["street-a"]

        def _hide_route_pick_dialog(self):
            pass

        def _stop_worker(self, t, *_a):
            if t:
                self.stopped.append(t)

        def _flush_install_form(self):
            self.flushed = True

        def _persist_shift(self, quiet=False):
            return self.save_ok

        def _counter_resume_gps(self):
            pass

    ended: list[str] = []
    stub = _Stub()
    stub.set(app_lifecycle, "end_session_clean", lambda d: ended.append(d))
    try:
        ok_win = _Win(True)
        check(ok_win._save_before_update_exit() is True, "real routine: save ok -> proceed")
        check("_picocount_thread" in ok_win.stopped and "street-a" in ok_win.stopped,
              "real routine: counter + street threads stopped")
        check(ok_win.flushed and ok_win.gps.stopped and len(ended) == 1,
              "real routine: install form flushed, GPS released, session closed")
        bad_win = _Win(False)
        check(bad_win._save_before_update_exit() is False, "real routine: save fails -> no exit")
        check(not bad_win.gps.stopped and len(ended) == 1,
              "real routine: failed save keeps GPS + session running")
    finally:
        stub.restore()


def _run_bat(app: str) -> int:
    env = {**os.environ, "TD_APPLY_NO_LAUNCH": "1"}
    return subprocess.run(
        ["cmd.exe", "/c", os.path.join(app, au.APPLY_BAT)],
        cwd=app, env=env, capture_output=True, text=True, timeout=180,
    ).returncode


def _fresh_app(tmp: str, *, ready_internal: bool = True) -> tuple[str, str, str]:
    app = os.path.join(tmp, "app dir")  # space in path like C:\MindLink AI
    data = os.path.join(app, "tds_data")
    _bundle(app, "old")
    ready = os.path.join(data, au.READY_DIRNAME)
    if ready_internal:
        _stage(ready, "new")
    else:
        _bundle(ready, "new", internal=False)
    au._write_apply_bat(app, ready, "1.0.20")
    return app, data, ready


def _leftovers(app: str) -> list[str]:
    return [n for n in os.listdir(app)
            if n.endswith(("_old", "_new", "_failed", "_stale", ".old", ".new", ".failed", ".stale"))]


def test_bat() -> None:
    print("[UPD-2 helper bat installs or rolls back]")
    if os.name != "nt":
        print("  SKIP not Windows")
        return
    running = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq TrafficDeployer.exe"], capture_output=True, text=True,
    ).stdout
    if "TrafficDeployer.exe" in running:
        print("  SKIP TrafficDeployer.exe is running on this PC (helper would wait for it)")
        return

    with tempfile.TemporaryDirectory() as tmp:
        app, data, _ = _fresh_app(tmp)
        _run_bat(app)
        check(_read(os.path.join(app, "TrafficDeployer.exe")) == "exe-new", "success: new exe")
        check(_read(os.path.join(app, "_internal", "lib.dll")) == "lib-new", "success: new _internal")
        check(_read(os.path.join(app, "web", "index.html")) == "web-new", "success: new web")
        check(not _leftovers(app), f"success: no leftovers {_leftovers(app)}")
        check(_read(os.path.join(data, ".update_applied")) == "1.0.20", "success: applied marker")

    with tempfile.TemporaryDirectory() as tmp:
        app, data, _ = _fresh_app(tmp)
        bat = os.path.join(app, au.APPLY_BAT)
        body = open(bat, encoding="ascii").read()
        needle = 'xcopy /e /i /y /q "%READY%\\_internal" _internal_new\\'
        check(needle in body, "copy failure: _internal copy step present")
        body = body.replace(needle, 'xcopy /e /i /y /q "%READY%\\no_such_dir" _internal_new\\')
        with open(bat, "w", encoding="ascii", newline="") as f:
            f.write(body)
        _run_bat(app)
        check(_read(os.path.join(app, "TrafficDeployer.exe")) == "exe-old", "copy failure: live exe untouched")
        check(_read(os.path.join(app, "_internal", "lib.dll")) == "lib-old", "copy failure: live _internal untouched")
        check(not _leftovers(app), f"copy failure: scratch cleaned {_leftovers(app)}")
        check(_read(os.path.join(data, au.FAILED_MARKER)) == "1.0.20", "copy failure: failed marker")

    with tempfile.TemporaryDirectory() as tmp:
        app, data, _ = _fresh_app(tmp)
        # A file held open in live web/ (Explorer, antivirus) blocks renaming web
        # after exe + _internal were already swapped -> rename-only rollback.
        held = open(os.path.join(app, "web", "index.html"), "rb")
        try:
            _run_bat(app)
        finally:
            held.close()
        check(_read(os.path.join(app, "TrafficDeployer.exe")) == "exe-old", "locked swap: old exe restored")
        check(_read(os.path.join(app, "_internal", "lib.dll")) == "lib-old", "locked swap: old _internal restored")
        check(_read(os.path.join(app, "web", "index.html")) == "web-old", "locked swap: old web intact")
        check(not _leftovers(app), f"locked swap: no leftovers {_leftovers(app)}")
        check(_read(os.path.join(data, au.FAILED_MARKER)) == "1.0.20", "locked swap: failed marker")
        check(not os.path.isfile(os.path.join(data, ".update_applied")), "locked swap: not marked applied")

    with tempfile.TemporaryDirectory() as tmp:
        app, data, _ = _fresh_app(tmp)
        # Earlier run died mid-swap: live _internal gone, good copy left as _internal_old.
        os.rename(os.path.join(app, "_internal"), os.path.join(app, "_internal_old"))
        _touch(os.path.join(app, "_internal_new", "partial.dll"), "partial")
        _touch(os.path.join(data, au.SWAP_MARKER), "1.0.19")
        _run_bat(app)
        check(_read(os.path.join(app, "_internal", "lib.dll")) == "lib-new", "interrupted run: recovers then installs")
        check(not _leftovers(app), f"interrupted run: no leftovers {_leftovers(app)}")
        check(not os.path.isfile(os.path.join(data, au.SWAP_MARKER)), "interrupted run: swap marker cleared")

    with tempfile.TemporaryDirectory() as tmp:
        app, data, _ = _fresh_app(tmp)
        # Successful earlier update could not retire its old build: stale _internal_old
        # beside a good live _internal and no swap marker -> must be deleted, not restored.
        _touch(os.path.join(app, "_internal_old", "lib.dll"), "lib-ancient")
        bat = os.path.join(app, au.APPLY_BAT)
        body = open(bat, encoding="ascii").read()
        body = body.replace('xcopy /e /i /y /q "%READY%\\_internal" _internal_new\\',
                            'xcopy /e /i /y /q "%READY%\\no_such_dir" _internal_new\\')
        with open(bat, "w", encoding="ascii", newline="") as f:
            f.write(body)
        _run_bat(app)
        check(_read(os.path.join(app, "_internal", "lib.dll")) == "lib-old",
              "stale old build: live copy kept, ancient build not restored")
        check(not os.path.isdir(os.path.join(app, "_internal_old")), "stale old build: deleted")

    with tempfile.TemporaryDirectory() as tmp:
        app, data, _ = _fresh_app(tmp)
        # App never closes: point the wait at a process that is running (this python)
        # and shorten the limit. Helper must give up without opening a second copy.
        bat = os.path.join(app, au.APPLY_BAT)
        me = os.path.basename(sys.executable)
        body = open(bat, encoding="ascii").read()
        body = body.replace('IMAGENAME eq TrafficDeployer.exe', f'IMAGENAME eq {me}')
        body = body.replace('find /I "TrafficDeployer.exe"', f'find /I "{me}"')
        body = body.replace("GEQ 120", "GEQ 2")
        with open(bat, "w", encoding="ascii", newline="") as f:
            f.write(body)
        rc = _run_bat(app)
        check(rc == 1, "app never closes: helper exits without the launch step")
        check(_read(os.path.join(app, "TrafficDeployer.exe")) == "exe-old", "app never closes: files untouched")
        check(_read(os.path.join(data, au.FAILED_MARKER)) == "1.0.20", "app never closes: failed marker")

    with tempfile.TemporaryDirectory() as tmp:
        app, data, _ = _fresh_app(tmp, ready_internal=False)
        _run_bat(app)
        check(_read(os.path.join(app, "TrafficDeployer.exe")) == "exe-old", "incomplete bundle: untouched")
        check(_read(os.path.join(data, au.FAILED_MARKER)) == "1.0.20", "incomplete bundle: failed marker")

    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pyw):
        print("  SKIP real launch (pythonw.exe not found)")
        return
    with tempfile.TemporaryDirectory() as tmp:
        app, data, _ = _fresh_app(tmp)
        bat = os.path.join(app, au.APPLY_BAT)
        code = (
            f"import sys; sys.path.insert(0, {ROOT!r}); "
            f"from core import auto_updater as au; au._launch_helper({bat!r}, {app!r})"
        )
        subprocess.run([pyw, "-c", code], env={**os.environ, "TD_APPLY_NO_LAUNCH": "1"}, timeout=60)
        marker = os.path.join(data, ".update_applied")
        deadline = time.time() + 90
        while time.time() < deadline and not os.path.isfile(marker):
            time.sleep(1)
        check(_read(marker) == "1.0.20", "real launch from windowed parent: helper finishes")
        check(_read(os.path.join(app, "TrafficDeployer.exe")) == "exe-new", "real launch: new exe installed")
        deadline = time.time() + 15
        while time.time() < deadline and os.path.isfile(bat):
            time.sleep(0.5)


def main() -> int:
    test_no_downgrade()
    test_no_relaunch_loop()
    test_save_before_exit()
    test_bat()
    print(f"\n{'PASS' if not FAILS else 'FAIL'} test_updater_safety ({len(FAILS)} failures)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
