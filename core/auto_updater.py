"""Wi‑Fi launch auto-update for portable installs (exe + _internal + web).

Preserves tds_data/. Configure channel via tds_data/update_channel.json.
Remote manifest (version.json): version, download_url, notes, sha256 (optional).

Windows cannot overwrite a running .exe — apply uses a helper .bat that waits
for this process to exit, then swaps files and relaunches.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass

from core import app_lifecycle, update_check
from ui.paths import APP_DIR, DATA_DIR, IS_PORTABLE

UPDATE_STATE_FILE = ".update_state.json"
STAGING_DIRNAME = "update_staging"
READY_DIRNAME = "update_ready"
BACKUP_DIRNAME = "backup_app"
APPLY_BAT = "apply_update_pending.bat"
# Fixed names — each download overwrites the previous (no versioned pile-up on the laptop).
STAGING_ZIP_NAME = "update.zip"
STAGING_EXTRACT_NAME = "extracted"
CHECK_COOLDOWN_S = 60
_UA = "TrafficDeployer-AutoUpdate/1.0"


@dataclass
class UpdateRunResult:
    checked: bool = False
    update_available: bool = False
    applied: bool = False
    relaunch: bool = False
    message: str = ""
    latest: str = ""
    error: str = ""


def _state_path(data_dir: str) -> str:
    return os.path.join(data_dir, UPDATE_STATE_FILE)


def _read_state(data_dir: str) -> dict:
    path = _state_path(data_dir)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(data_dir: str, data: dict) -> None:
    path = _state_path(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _should_check_now(data_dir: str, *, force: bool) -> bool:
    if force:
        return True
    state = _read_state(data_dir)
    last = str(state.get("last_check_at") or "")
    if not last:
        return True
    try:
        from datetime import datetime, timezone

        then = datetime.fromisoformat(last.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - then).total_seconds()
        return age >= CHECK_COOLDOWN_S
    except (TypeError, ValueError):
        return True


def _bundle_root(extracted: str) -> str:
    """Zip may be flat or contain a single TrafficDeployer/ folder."""
    exe = os.path.join(extracted, "TrafficDeployer.exe")
    if os.path.isfile(exe):
        return extracted
    for name in os.listdir(extracted):
        sub = os.path.join(extracted, name)
        if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "TrafficDeployer.exe")):
            return sub
    return extracted


def validate_bundle(root: str) -> tuple[bool, str]:
    exe = os.path.join(root, "TrafficDeployer.exe")
    if not os.path.isfile(exe):
        return False, "TrafficDeployer.exe missing in update bundle"
    internal_web = os.path.join(root, "_internal", "web", "index.html")
    side_web = os.path.join(root, "web", "index.html")
    if not os.path.isfile(internal_web) and not os.path.isfile(side_web):
        return False, "Map UI missing (_internal/web or web/)"
    if not os.path.isdir(os.path.join(root, "_internal")):
        return False, "_internal folder missing"
    return True, ""


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: str, timeout: float = 600.0) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        with open(dest, "wb") as out:
            shutil.copyfileobj(resp, out)


def _extract_zip(zip_path: str, dest: str) -> str:
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)
    return _bundle_root(dest)


def _replace_tree(src: str, dst: str) -> None:
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _backup_current(app_dir: str, data_dir: str) -> str:
    backup = os.path.join(data_dir, BACKUP_DIRNAME)
    if os.path.isdir(backup):
        shutil.rmtree(backup)
    os.makedirs(backup, exist_ok=True)
    exe = os.path.join(app_dir, "TrafficDeployer.exe")
    if os.path.isfile(exe):
        shutil.copy2(exe, os.path.join(backup, "TrafficDeployer.exe"))
    for name in ("_internal", "web"):
        src = os.path.join(app_dir, name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(backup, name))
    return backup


def _restore_backup(app_dir: str, data_dir: str) -> None:
    backup = os.path.join(data_dir, BACKUP_DIRNAME)
    if not os.path.isdir(backup):
        return
    exe = os.path.join(backup, "TrafficDeployer.exe")
    if os.path.isfile(exe):
        _install_exe(exe, os.path.join(app_dir, "TrafficDeployer.exe"))
    for name in ("_internal", "web"):
        src = os.path.join(backup, name)
        dst = os.path.join(app_dir, name)
        if os.path.isdir(src):
            _replace_tree(src, dst)


def _install_exe(src: str, dst: str) -> None:
    """Install exe; on Windows rename the locked running binary first."""
    pending = dst + ".pending"
    old = dst + ".old"
    for path in (pending, old):
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    shutil.copy2(src, pending)
    if os.path.isfile(dst):
        try:
            os.replace(dst, old)
        except OSError:
            # Last resort: try direct overwrite (works if process already exited)
            pass
    try:
        os.replace(pending, dst)
    except OSError:
        shutil.copy2(pending, dst)
        try:
            os.remove(pending)
        except OSError:
            pass


def _write_apply_bat(app_dir: str, ready_dir: str, version: str) -> str:
    """Helper runs after this process exits — required on Windows."""
    bat_path = os.path.join(app_dir, APPLY_BAT)
    ready = ready_dir.replace("/", "\\")
    app = app_dir.replace("/", "\\")
    log = os.path.join(app, "tds_data", "update_apply.log").replace("/", "\\")
    lines = [
        "@echo off",
        "setlocal EnableExtensions",
        f'cd /d "{app}"',
        f'echo [%date% %time%] apply start v{version}> "{log}"',
        "echo Applying Traffic Deployer update v" + version + "...",
        "echo Waiting for app to close...",
        "set /a WAITS=0",
        ":wait",
        'tasklist /FI "IMAGENAME eq TrafficDeployer.exe" 2>nul | find /I "TrafficDeployer.exe" >nul',
        "if not errorlevel 1 (",
        "  set /a WAITS+=1",
        "  if %WAITS% GEQ 120 (",
        f'    echo [%date% %time%] FAIL: app still running after 120s>> "{log}"',
        "    echo FAIL: TrafficDeployer.exe still running. Close it in Task Manager.",
        "    pause",
        "    exit /b 1",
        "  )",
        "  timeout /t 1 /nobreak >nul",
        "  goto wait",
        ")",
        "timeout /t 2 /nobreak >nul",
        f'set "READY={ready}"',
        'if not exist "%READY%\\TrafficDeployer.exe" (',
        f'  echo [%date% %time%] FAIL: ready exe missing>> "{log}"',
        "  echo FAIL: update files missing in tds_data\\update_ready",
        "  pause",
        "  exit /b 1",
        ")",
        "if exist TrafficDeployer.exe.old del /f /q TrafficDeployer.exe.old >nul 2>&1",
        "if exist TrafficDeployer.exe (",
        "  ren TrafficDeployer.exe TrafficDeployer.exe.old",
        "  if errorlevel 1 (",
        f'    echo [%date% %time%] FAIL: could not rename running exe>> "{log}"',
        "    echo FAIL: could not replace TrafficDeployer.exe - close the app and retry FINISH_UPDATE.bat",
        "    pause",
        "    exit /b 1",
        "  )",
        ")",
        'copy /y "%READY%\\TrafficDeployer.exe" TrafficDeployer.exe >nul',
        "if errorlevel 1 (",
        f'  echo [%date% %time%] FAIL: copy exe>> "{log}"',
        "  if exist TrafficDeployer.exe.old ren TrafficDeployer.exe.old TrafficDeployer.exe",
        "  echo FAIL: could not copy new exe",
        "  pause",
        "  exit /b 1",
        ")",
        "if exist _internal_old rmdir /s /q _internal_old >nul 2>&1",
        "if exist _internal ren _internal _internal_old",
        'xcopy /e /i /y "%READY%\\_internal" _internal\\ >nul',
        "if errorlevel 1 (",
        f'  echo [%date% %time%] FAIL: xcopy _internal>> "{log}"',
        "  echo FAIL: could not copy _internal",
        "  pause",
        "  exit /b 1",
        ")",
        "if exist web_old rmdir /s /q web_old >nul 2>&1",
        "if exist web ren web web_old",
        'if exist "%READY%\\web\\" xcopy /e /i /y "%READY%\\web" web\\ >nul',
        'if exist "%READY%\\OPEN_APP.bat" copy /y "%READY%\\OPEN_APP.bat" OPEN_APP.bat >nul 2>&1',
        'if exist "%READY%\\VERSION.txt" copy /y "%READY%\\VERSION.txt" VERSION.txt >nul 2>&1',
        'if exist "%READY%\\READ_ME_FIRST.txt" copy /y "%READY%\\READ_ME_FIRST.txt" READ_ME_FIRST.txt >nul 2>&1',
        "rmdir /s /q _internal_old >nul 2>&1",
        "rmdir /s /q web_old >nul 2>&1",
        "del /f /q TrafficDeployer.exe.old >nul 2>&1",
        f'echo {version}> "tds_data\\.update_applied"',
        f'echo [%date% %time%] OK applied v{version}>> "{log}"',
        "echo Update applied. Starting v" + version + "...",
        'start "" "%~dp0TrafficDeployer.exe"',
        f'del /f /q "%~f0" >nul 2>&1',
        "exit /b 0",
        "",
    ]
    with open(bat_path, "w", encoding="ascii", newline="\r\n") as f:
        f.write("\n".join(lines))
    return bat_path


def ready_bundle_path(data_dir: str | None = None) -> str | None:
    """Return tds_data/update_ready if a staged exe is present (stalled Wi-Fi apply)."""
    data_dir = data_dir or DATA_DIR
    ready = os.path.join(data_dir, READY_DIRNAME)
    if os.path.isfile(os.path.join(ready, "TrafficDeployer.exe")):
        return ready
    return None


def resume_pending_apply(
    current_version: str,
    *,
    app_dir: str | None = None,
    data_dir: str | None = None,
) -> UpdateRunResult | None:
    """If a prior download left update_ready, finish the file swap (no re-download)."""
    app_dir = app_dir or APP_DIR
    data_dir = data_dir or DATA_DIR
    ready = ready_bundle_path(data_dir)
    if not ready:
        return None
    state = _read_state(data_dir)
    pending = str(state.get("pending_apply") or "").strip()
    version = pending or "pending"
    ok, detail = validate_bundle(ready)
    if not ok:
        return UpdateRunResult(
            checked=True,
            error=detail,
            message=f"Staged update invalid: {detail}",
        )
    result = UpdateRunResult(
        checked=True,
        update_available=True,
        applied=True,
        relaunch=True,
        latest=version,
        message=f"Finishing staged update v{version} (no re-download)…",
    )
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is not None:
            QMessageBox.information(
                None,
                "Traffic Deployer update",
                f"A downloaded update is ready (v{version}).\n\n"
                "App will close, finish installing, then reopen.\n"
                f"Current: v{current_version}",
            )
    except Exception:
        pass
    schedule_apply_and_exit(ready, app_dir, data_dir, version)
    return result


def _clear_staging(data_dir: str) -> None:
    """Drop tds_data/update_staging so prior downloads do not accumulate."""
    staging = os.path.join(data_dir, STAGING_DIRNAME)
    if os.path.isdir(staging):
        try:
            shutil.rmtree(staging)
        except OSError:
            pass


def stage_bundle_for_apply(bundle_root: str, data_dir: str) -> str:
    """Copy validated bundle into tds_data/update_ready for the helper bat."""
    ready = os.path.join(data_dir, READY_DIRNAME)
    if os.path.isdir(ready):
        shutil.rmtree(ready)
    os.makedirs(ready, exist_ok=True)
    shutil.copy2(
        os.path.join(bundle_root, "TrafficDeployer.exe"),
        os.path.join(ready, "TrafficDeployer.exe"),
    )
    _replace_tree(
        os.path.join(bundle_root, "_internal"),
        os.path.join(ready, "_internal"),
    )
    src_web = os.path.join(bundle_root, "web")
    if os.path.isdir(src_web):
        _replace_tree(src_web, os.path.join(ready, "web"))
    elif os.path.isdir(os.path.join(bundle_root, "_internal", "web")):
        _replace_tree(
            os.path.join(bundle_root, "_internal", "web"),
            os.path.join(ready, "web"),
        )
    for name in ("OPEN_APP.bat", "APP_UPDATE.txt", "READ_ME_FIRST.txt", "VERSION.txt"):
        src = os.path.join(bundle_root, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(ready, name))
    # Staging extract/zip no longer needed — free disk before restart.
    _clear_staging(data_dir)
    return ready


def apply_bundle(bundle_root: str, app_dir: str, data_dir: str) -> None:
    """Replace portable binaries while app is closed; never touches tds_data/."""
    ok, detail = validate_bundle(bundle_root)
    if not ok:
        raise RuntimeError(detail)
    _backup_current(app_dir, data_dir)
    try:
        _install_exe(
            os.path.join(bundle_root, "TrafficDeployer.exe"),
            os.path.join(app_dir, "TrafficDeployer.exe"),
        )
        _replace_tree(
            os.path.join(bundle_root, "_internal"),
            os.path.join(app_dir, "_internal"),
        )
        src_web = os.path.join(bundle_root, "web")
        if os.path.isdir(src_web):
            _replace_tree(src_web, os.path.join(app_dir, "web"))
        elif os.path.isdir(os.path.join(bundle_root, "_internal", "web")):
            _replace_tree(
                os.path.join(bundle_root, "_internal", "web"),
                os.path.join(app_dir, "web"),
            )
    except Exception:
        _restore_backup(app_dir, data_dir)
        raise


def schedule_apply_and_exit(
    bundle_root: str,
    app_dir: str,
    data_dir: str,
    version: str,
) -> None:
    """Stage files, start helper bat, exit so Windows can replace the exe."""
    ok, detail = validate_bundle(bundle_root)
    if not ok:
        raise RuntimeError(detail)
    ready_target = os.path.join(data_dir, READY_DIRNAME)
    # Already staged (resume) — do not rmtree+copy onto itself.
    if os.path.normcase(os.path.abspath(bundle_root)) == os.path.normcase(
        os.path.abspath(ready_target)
    ):
        ready = ready_target
        _clear_staging(data_dir)  # drop leftover download if still present
    else:
        ready = stage_bundle_for_apply(bundle_root, data_dir)
    bat = _write_apply_bat(app_dir, ready, version)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    subprocess.Popen(
        ["cmd.exe", "/c", bat],
        cwd=app_dir,
        creationflags=flags,
        close_fds=True,
    )
    sys.exit(0)


def relaunch_and_exit(app_dir: str) -> None:
    exe = os.path.join(app_dir, "TrafficDeployer.exe")
    if not os.path.isfile(exe):
        return
    flags = getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        [exe],
        cwd=app_dir,
        creationflags=flags,
        close_fds=True,
    )
    sys.exit(0)


def check_and_apply(
    current_version: str,
    *,
    app_dir: str | None = None,
    data_dir: str | None = None,
    field_mode: bool = False,
    allow_apply: bool | None = None,
    force_check: bool = False,
) -> UpdateRunResult:
    """Check manifest, optionally download and apply. Skips when field mode is on."""
    app_dir = app_dir or APP_DIR
    data_dir = data_dir or DATA_DIR
    allow_apply = IS_PORTABLE if allow_apply is None else allow_apply

    if field_mode:
        return UpdateRunResult(message="Field mode — updates wait until I'm online at home.")

    if not _should_check_now(data_dir, force=force_check):
        return UpdateRunResult(message="Update check skipped (recently checked).")

    info = update_check.check_for_update(current_version)
    state = _read_state(data_dir)
    state["last_check_at"] = update_check.utc_now_iso()
    state["last_current"] = current_version
    _write_state(data_dir, state)

    result = UpdateRunResult(checked=True, latest=info.latest, error=info.error)
    if info.error:
        result.message = info.error
        return result
    if not info.update_available:
        result.message = "Up to date."
        state["last_latest"] = info.latest
        _write_state(data_dir, state)
        return result

    result.update_available = True
    if not allow_apply:
        result.message = f"Update {info.latest} available (dev mode — apply on work laptop)."
        return result
    if not info.download_url:
        result.message = f"Update {info.latest} listed but no download_url in manifest."
        return result

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is not None:
            QMessageBox.information(
                None,
                "Traffic Deployer update",
                f"Update v{info.latest} found.\n\n"
                "Downloading ~300 MB over Wi‑Fi.\n"
                "App will close, apply the update, then reopen.",
            )
    except Exception:
        pass

    # Wipe prior staging first — one overwrite slot, not a growing stack of versions.
    _clear_staging(data_dir)
    staging_root = os.path.join(data_dir, STAGING_DIRNAME)
    os.makedirs(staging_root, exist_ok=True)
    zip_path = os.path.join(staging_root, STAGING_ZIP_NAME)
    extract_dir = os.path.join(staging_root, STAGING_EXTRACT_NAME)

    try:
        _download(info.download_url, zip_path)
        if info.sha256:
            digest = _sha256_file(zip_path)
            if digest.lower() != info.sha256.lower():
                raise RuntimeError("Download checksum mismatch — update rejected.")
        bundle_root = _extract_zip(zip_path, extract_dir)
        # Drop zip after extract — keep only extracted until staged to update_ready.
        try:
            if os.path.isfile(zip_path):
                os.remove(zip_path)
        except OSError:
            pass
        # Pending until helper bat writes tds_data/.update_applied — not "done" yet.
        state = _read_state(data_dir)
        state["last_latest"] = info.latest
        state["pending_apply"] = info.latest
        state["pending_at"] = update_check.utc_now_iso()
        _write_state(data_dir, state)
        result.applied = True
        result.relaunch = True
        result.message = f"Update v{info.latest} downloaded. Applying and restarting…"
        # Does not return — process exits so Windows can replace the exe.
        # stage_bundle_for_apply clears update_staging after copy to update_ready.
        schedule_apply_and_exit(bundle_root, app_dir, data_dir, info.latest)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        result.error = str(exc)
        result.message = f"Update failed: {exc}"
        return result

    return result


def _clear_pending_if_current(current_version: str, data_dir: str) -> None:
    """After a successful launch on the new build, clear pending / mark applied."""
    applied_marker = os.path.join(data_dir, ".update_applied")
    state = _read_state(data_dir)
    pending = str(state.get("pending_apply") or "").strip()
    marker_ver = ""
    if os.path.isfile(applied_marker):
        try:
            with open(applied_marker, encoding="utf-8") as f:
                marker_ver = f.read().strip()
        except OSError:
            marker_ver = ""
    done_ver = marker_ver or (
        current_version if pending and current_version == pending else ""
    )
    if done_ver and done_ver == current_version:
        state["last_applied"] = current_version
        state["last_applied_at"] = update_check.utc_now_iso()
        state.pop("pending_apply", None)
        state.pop("pending_at", None)
        _write_state(data_dir, state)
        ready = os.path.join(data_dir, READY_DIRNAME)
        if os.path.isdir(ready):
            try:
                shutil.rmtree(ready)
            except OSError:
                pass
        _clear_staging(data_dir)
        try:
            if os.path.isfile(applied_marker):
                os.remove(applied_marker)
        except OSError:
            pass


def maybe_apply_on_launch(current_version: str) -> UpdateRunResult:
    """Portable startup gate — resume stalled apply, then Wi‑Fi check (home mode)."""
    _clear_pending_if_current(current_version, DATA_DIR)
    resumed = resume_pending_apply(current_version)
    if resumed is not None:
        return resumed
    field = app_lifecycle.load_persisted_field_mode(DATA_DIR)
    # OPEN_APP / WIFI_UPDATE_NOW set TD_UPDATE_* when launching on home Wi‑Fi —
    # do not skip the check just because last session left field mode on.
    if os.environ.get("TD_UPDATE_URL", "").strip() or os.environ.get("TD_UPDATE_HOME", "").strip():
        field = False
    channel = bool(update_check.channel_url())
    force = (
        channel
        or app_lifecycle.previous_exit_unclean(DATA_DIR)
        or app_lifecycle.prior_session_errors(DATA_DIR) >= 3
    )
    return check_and_apply(
        current_version,
        field_mode=field,
        force_check=force,
    )
