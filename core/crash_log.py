"""Field crash / error logs under tds_data/crashes/ for USB handoff to creator laptop."""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime

from ui.paths import CRASH_DIR

_last_action = "app start"


def set_last_action(label: str) -> None:
    global _last_action
    _last_action = (label or "")[:240]


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _write(filename: str, body: str) -> str:
    path = os.path.join(CRASH_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


def log_error(
    exc: BaseException,
    *,
    context: str = "",
    extra: dict | None = None,
) -> str:
    """Append a timestamped log; returns path written."""
    lines = [
        f"time: {datetime.now().isoformat(timespec='seconds')}",
        f"context: {context or 'error'}",
        f"last_action: {_last_action}",
        f"exception: {type(exc).__name__}: {exc}",
        "",
        traceback.format_exc(),
    ]
    if extra:
        lines.append("")
        lines.append("extra:")
        for k, v in extra.items():
            lines.append(f"  {k}: {v}")
    try:
        from core import picocount

        lines.append("")
        lines.append("com_ports:")
        for p in picocount.list_serial_ports():
            tag = "gps" if picocount.is_gps_port(p) else (
                "counter" if picocount.is_counter_port(p) else "other")
            lines.append(f"  {p} ({tag})")
    except Exception:
        pass
    name = f"error_{_stamp()}.log"
    return _write(name, "\n".join(lines) + "\n")


def log_unhandled(exc_type, exc, tb) -> None:
    if exc_type is KeyboardInterrupt:
        sys.__excepthook__(exc_type, exc, tb)
        return
    body = "".join(traceback.format_exception(exc_type, exc, tb))
    header = (
        f"time: {datetime.now().isoformat(timespec='seconds')}\n"
        f"last_action: {_last_action}\n"
        f"unhandled: {exc_type.__name__}: {exc}\n\n"
    )
    _write(f"crash_{_stamp()}.log", header + body)
    sys.__excepthook__(exc_type, exc, tb)


def install_crash_logging() -> None:
    sys.excepthook = log_unhandled
