"""Checks before enabling offline field mode."""
from __future__ import annotations


def evaluate(
    field_report: dict,
    *,
    has_stops: bool,
    route_miles: float,
    graph_loaded: bool,
    route_graph_uncovered: bool = False,
) -> dict:
    """Return {ok, blockers[], warns[]} for READY FOR OFFLINE."""
    blockers: list[str] = []
    warns: list[str] = []

    for item in field_report.get("items", []):
        if item.get("level") == "fail":
            detail = item.get("detail", "").strip()
            blockers.append(f"{item['label']}" + (f" — {detail}" if detail else ""))

    if has_stops:
        if route_miles <= 0 or not field_report.get("field_ready", True):
            pass  # route check below
        if route_miles <= 0:
            blockers.append(
                "No built route — tap Apply route on Route tab after picking order, "
                "or BUILD ROUTE -> Suggest route."
            )
        if route_graph_uncovered:
            blockers.append(
                "Road map does not cover this job — download road map on Setup "
                "with this Excel/.EST loaded, BUILD ROUTE again, then go offline."
            )
        elif not graph_loaded:
            blockers.append(
                "No road map for this job — download or import road_graph.graphml on Setup."
            )
    elif not graph_loaded:
        warns.append(
            "No road graph saved yet — download or import road_graph.graphml before field work."
        )

    return {"ok": not blockers, "blockers": blockers, "warns": warns}
