"""Home setup checklist before READY FOR OFFLINE (P33)."""
from __future__ import annotations

from core.state import DEFAULT_HOME


def _home_ok(home: tuple[float, float], default_home: tuple | None) -> bool:
    if default_home:
        return True
    return (
        abs(float(home[0]) - DEFAULT_HOME[0]) > 1e-4
        or abs(float(home[1]) - DEFAULT_HOME[1]) > 1e-4
    )


def evaluate(
    *,
    home: tuple[float, float],
    default_home: tuple | None,
    excel_paths: list,
    est_paths: list,
    has_graph: bool,
    route_miles: float,
    field_report: dict | None = None,
) -> dict:
    """Return {ok, items: [{id, label, ok, detail}], blockers: [str]}."""
    items: list[dict] = []
    blockers: list[str] = []

    ok_start = _home_ok(home, default_home)
    items.append({
        "id": "start",
        "label": "Starting point set",
        "ok": ok_start,
        "detail": "" if ok_start else "GPS, address search, or save DEFAULT start",
    })
    if not ok_start:
        blockers.append("Set your starting point (not factory default).")

    ok_files = bool(excel_paths) and bool(est_paths)
    items.append({
        "id": "files",
        "label": "Excel + .EST loaded",
        "ok": ok_files,
        "detail": f"{len(excel_paths)} Excel, {len(est_paths)} EST" if ok_files else "Add both file types",
    })
    if not ok_files:
        blockers.append("Add at least one Excel/CSV and one .EST map.")

    ok_graph = has_graph
    items.append({
        "id": "roads",
        "label": "Road map on laptop",
        "ok": ok_graph,
        "detail": "Download or import road_graph.graphml" if not ok_graph else "Local graph ready",
    })
    if not ok_graph:
        blockers.append("Download or import the road map for your work area.")

    ok_route = route_miles > 0.05
    items.append({
        "id": "build",
        "label": "Route built",
        "ok": ok_route,
        "detail": f"{route_miles:.1f} mi" if ok_route else "Press BUILD OPTIMIZED ROUTE",
    })
    if not ok_route:
        blockers.append("Build your optimized route before leaving.")

    if field_report:
        for it in field_report.get("items", []):
            if it.get("level") == "fail":
                fid = it.get("id", "field")
                items.append({
                    "id": f"field_{fid}",
                    "label": it.get("label", "Field readiness"),
                    "ok": False,
                    "detail": it.get("detail", ""),
                })
                blockers.append(it.get("label", "Field readiness issue"))

    return {"ok": not blockers, "items": items, "blockers": blockers}


def route_summary(stops: list, route: dict) -> dict:
    """Post-build stats for UI (P35)."""
    miles = float(route.get("miles", 0) or 0)
    zones = sorted({int(s["route_zone"]) for s in stops if s.get("route_zone") is not None})
    on_graph = bool(route.get("graph"))
    return {
        "stops": len(stops),
        "miles": miles,
        "zones": len(zones),
        "zone_list": zones,
        "on_graph": on_graph,
        "text": (
            f"{len(stops)} stops · {miles:.1f} mi · {len(zones)} zone(s) · "
            f"{'real roads' if on_graph else 'segment lines only'}"
        ),
    }
