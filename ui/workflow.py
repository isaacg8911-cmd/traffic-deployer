"""Setup workflow step states (Start → Files → Road map → Build → Drive)."""
from __future__ import annotations

from core.state import DEFAULT_HOME

STEPS = (
    ("start", "Start"),
    ("files", "Files"),
    ("roads", "Road map"),
    ("build", "Build"),
    ("drive", "Go field"),
)


def _home_ok(home: tuple[float, float], default_home: tuple | None) -> bool:
    if default_home:
        return True
    return (
        abs(float(home[0]) - DEFAULT_HOME[0]) > 1e-4
        or abs(float(home[1]) - DEFAULT_HOME[1]) > 1e-4
    )


def compute_workflow(
    *,
    home: tuple[float, float],
    default_home: tuple | None,
    excel_paths: list,
    est_paths: list,
    has_graph: bool,
    route_miles: float,
    offline_mode: bool = False,
) -> list[dict]:
    """Each step: {id, label, status} where status is done | current | pending."""
    route_ok = route_miles > 0.05
    done_map = {
        "start": _home_ok(home, default_home),
        "files": bool(excel_paths) and bool(est_paths),
        "roads": has_graph,
        "build": route_ok,
        "drive": offline_mode,
    }
    current_id = "drive"
    for sid, _ in STEPS:
        if not done_map.get(sid):
            current_id = sid
            break
    out: list[dict] = []
    for sid, label in STEPS:
        if done_map.get(sid):
            status = "done"
        elif sid == current_id:
            status = "current"
        else:
            status = "pending"
        out.append({"id": sid, "label": label, "status": status})
    return out
