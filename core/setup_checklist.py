"""Home setup checklist before READY FOR OFFLINE (P33)."""
from __future__ import annotations

from core.state import DEFAULT_HOME, RouteState


def road_map_covers_job(data_dir: str, stops: list[dict]) -> tuple[bool, str]:
    """True when the saved road graph spans this job's sites (not a different county)."""
    if not stops:
        return True, ""
    import road_router
    from core.routing import graph_covers_stops

    if not road_router.has_graph(data_dir):
        return False, "Download or import road_graph.graphml"
    graph = road_router.load_graph(data_dir)
    if graph is None:
        return False, "Road map on disk but will not load — re-import from home PC"
    if graph_covers_stops(graph, stops):
        return True, "Covers this job"
    return False, "Saved map is for a different area — Setup → Download with this job loaded"


def _home_ok(home: tuple[float, float], default_home: tuple | None) -> bool:
    """Current session start must not be the factory demo coords.

    Saved default alone is not enough — READY FOR OFFLINE uses ``home``.
    """
    _ = default_home  # kept for call-site compatibility
    return not RouteState.is_factory_home(home[0], home[1])


def evaluate(
    *,
    home: tuple[float, float],
    default_home: tuple | None,
    excel_paths: list,
    est_paths: list,
    has_graph: bool,
    route_miles: float,
    field_report: dict | None = None,
    stops: list[dict] | None = None,
    data_dir: str = "",
    route_graph_uncovered: bool = False,
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

    covers, cover_detail = True, ""
    if stops and data_dir:
        covers, cover_detail = road_map_covers_job(data_dir, stops)
    elif route_graph_uncovered:
        covers = False
        cover_detail = "Road map does not cover this job"
    ok_graph = has_graph and covers
    road_detail = cover_detail if has_graph else "Download or import road_graph.graphml"
    items.append({
        "id": "roads",
        "label": "Road map covers this job",
        "ok": ok_graph,
        "detail": road_detail if ok_graph else (road_detail or "Download or import road_graph.graphml"),
    })
    if not has_graph:
        blockers.append("Download or import the road map for your work area.")
    elif not covers:
        blockers.append(
            "Road map does not cover these sites — Setup → Download road map "
            "while this Excel/.EST job is loaded, then BUILD ROUTE again."
        )

    ok_route = route_miles > 0.05
    items.append({
        "id": "build",
        "label": "Route built",
        "ok": ok_route,
        "detail": (
            f"{route_miles:.1f} mi"
            if ok_route
            else "Tap Apply route on Route tab (or BUILD ROUTE -> Suggest route)"
        ),
    })
    if not ok_route:
        blockers.append(
            "Finish the route — tap Apply route on Route tab after picking order, "
            "or use BUILD ROUTE -> Suggest route."
        )

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
    uncovered = bool(route.get("graph_uncovered"))
    if on_graph:
        kind = "real roads"
    elif uncovered:
        kind = "straight-line (wrong map area)"
    else:
        kind = "straight-line (no road map)"
    return {
        "stops": len(stops),
        "miles": miles,
        "zones": len(zones),
        "zone_list": zones,
        "on_graph": on_graph,
        "text": _route_summary_text(len(stops), miles, len(zones), kind, route),
    }


def _route_summary_text(n: int, miles: float, nzones: int, kind: str, route: dict) -> str:
    base = f"{n} stops · {miles:.1f} mi · {nzones} zone(s) · {kind}"
    try:
        from core.time_est import summary_clause
        extra = summary_clause(route)
    except Exception:
        extra = ""
    if extra:
        return f"{base} · {extra}"
    return base
