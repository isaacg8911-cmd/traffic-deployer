"""Session markers for clean exit, crash recovery, and update urgency."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

try:
    import persistence
except Exception:
    persistence = None

SESSION_MARKER = ".session_active"
EXIT_STATE_FILE = ".exit_state.json"
HEALTH_FILE = ".session_health.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _paths(data_dir: str) -> tuple[str, str, str]:
    return (
        os.path.join(data_dir, SESSION_MARKER),
        os.path.join(data_dir, EXIT_STATE_FILE),
        os.path.join(data_dir, HEALTH_FILE),
    )


def begin_session(data_dir: str) -> None:
    """Mark this process as active; record whether the previous exit was unclean."""
    marker, exit_state, health_path = _paths(data_dir)
    prev = _read_json(exit_state)
    unclean = prev.get("clean") is False or os.path.isfile(marker)
    health_data = _read_json(health_path)
    prior_errors = int(health_data.get("runtime_errors", 0))
    if unclean:
        health_data["unclean_exit"] = True
        health_data["unclean_at"] = _utc_now()
    health_data["prior_session_errors"] = prior_errors
    health_data["session_started_at"] = _utc_now()
    health_data["runtime_errors"] = 0
    _write_json(health_path, health_data)
    with open(marker, "w", encoding="utf-8") as f:
        f.write(f"pid={os.getpid()} started={_utc_now()}\n")


def end_session_clean(data_dir: str) -> None:
    """Clear active marker and record a clean shutdown."""
    marker, exit_state, _ = _paths(data_dir)
    if os.path.isfile(marker):
        try:
            os.remove(marker)
        except OSError:
            pass
    _write_json(exit_state, {"clean": True, "at": _utc_now()})
    health = _read_json(os.path.join(data_dir, HEALTH_FILE))
    health["unclean_exit"] = False
    _write_json(os.path.join(data_dir, HEALTH_FILE), health)


def mark_unclean_exit(data_dir: str, *, reason: str = "") -> None:
    """Hard crash or unhandled exception — next launch should prioritize updates."""
    _, exit_state, health_path = _paths(data_dir)
    _write_json(exit_state, {"clean": False, "at": _utc_now(), "reason": reason[:240]})
    health = _read_json(health_path)
    health["unclean_exit"] = True
    health["unclean_at"] = _utc_now()
    if reason:
        health["unclean_reason"] = reason[:240]
    _write_json(health_path, health)


def note_runtime_error(data_dir: str) -> None:
    """Handled error while the UI keeps running — still signals instability."""
    health_path = os.path.join(data_dir, HEALTH_FILE)
    health = _read_json(health_path)
    health["runtime_errors"] = int(health.get("runtime_errors", 0)) + 1
    health["last_error_at"] = _utc_now()
    _write_json(health_path, health)


def previous_exit_unclean(data_dir: str) -> bool:
    health = _read_json(os.path.join(data_dir, HEALTH_FILE))
    if health.get("unclean_exit"):
        return True
    exit_state = _read_json(os.path.join(data_dir, EXIT_STATE_FILE))
    return exit_state.get("clean") is False


def prior_session_errors(data_dir: str) -> int:
    return int(_read_json(os.path.join(data_dir, HEALTH_FILE)).get("prior_session_errors", 0))


def runtime_errors_this_session(data_dir: str) -> int:
    return int(_read_json(os.path.join(data_dir, HEALTH_FILE)).get("runtime_errors", 0))


def load_persisted_field_mode(data_dir: str, profile: str = "DEFAULT") -> bool:
    """Read offline_mode from encrypted shift state without starting the UI."""
    if persistence is None:
        return False
    backup = os.path.join(data_dir, f"tds_backup_{profile}.json")
    data = persistence.load_state(backup, data_dir)
    return bool(data.get("offline_mode", False))
