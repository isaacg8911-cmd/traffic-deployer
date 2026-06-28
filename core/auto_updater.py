"""Wi‑Fi launch auto-update for portable installs (exe + _internal + web).

Preserves tds_data/. Configure channel via tds_data/update_channel.json.
Remote manifest (version.json): version, download_url, notes, sha256 (optional).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass

from core import app_lifecycle, update_check
from ui.paths import APP_DIR, DATA_DIR, IS_PORTABLE

UPDATE_STATE_FILE = ".update_state.json"
STAGING_DIRNAME = "update_staging"
BACKUP_DIRNAME = "backup_app"
CHECK_COOLDOWN_S = 4 * 3600
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
        shutil.copy2(exe, os.path.join(app_dir, "TrafficDeployer.exe"))
    for name in ("_internal", "web"):
        src = os.path.join(backup, name)
        dst = os.path.join(app_dir, name)
        if os.path.isdir(src):
            _replace_tree(src, dst)


def apply_bundle(bundle_root: str, app_dir: str, data_dir: str) -> None:
    """Replace portable binaries; never touches tds_data/."""
    ok, detail = validate_bundle(bundle_root)
    if not ok:
        raise RuntimeError(detail)
    _backup_current(app_dir, data_dir)
    try:
        shutil.copy2(
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

    staging_root = os.path.join(data_dir, STAGING_DIRNAME)
    os.makedirs(staging_root, exist_ok=True)
    zip_path = os.path.join(staging_root, f"TrafficDeployer-{info.latest}.zip")
    extract_dir = os.path.join(staging_root, f"extracted-{info.latest}")

    try:
        if os.path.isdir(extract_dir):
            shutil.rmtree(extract_dir)
        _download(info.download_url, zip_path)
        if info.sha256:
            digest = _sha256_file(zip_path)
            if digest.lower() != info.sha256.lower():
                raise RuntimeError("Download checksum mismatch — update rejected.")
        bundle_root = _extract_zip(zip_path, extract_dir)
        apply_bundle(bundle_root, app_dir, data_dir)
    except Exception as exc:  # noqa: BLE001
        result.error = str(exc)
        result.message = f"Update failed: {exc}"
        return result
    finally:
        try:
            if os.path.isfile(zip_path):
                os.remove(zip_path)
        except OSError:
            pass

    state = _read_state(data_dir)
    state["last_applied"] = info.latest
    state["last_applied_at"] = update_check.utc_now_iso()
    state["last_latest"] = info.latest
    _write_state(data_dir, state)

    result.applied = True
    result.relaunch = True
    notes = f" ({info.notes})" if info.notes else ""
    result.message = f"Updated to v{info.latest}{notes}. Restarting…"
    return result


def maybe_apply_on_launch(current_version: str) -> UpdateRunResult:
    """Portable startup gate — Wi‑Fi + home mode only."""
    field = app_lifecycle.load_persisted_field_mode(DATA_DIR)
    force = app_lifecycle.previous_exit_unclean(DATA_DIR) or app_lifecycle.prior_session_errors(DATA_DIR) >= 3
    return check_and_apply(
        current_version,
        field_mode=field,
        force_check=force,
    )
