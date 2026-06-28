"""Qt-free map/state payload builder shared by the mobile web backend.

The desktop app builds its map payload inside the Qt controller
(`ui/controllers/map_sync.py:_push_state_body`). That path is tightly coupled to
PySide widgets, so the mobile lane uses these pure helpers instead. Both consume
the same stop dict shape produced by `core.ingest.new_stop`, so the map renderer
stays consistent across desktop and phone.
"""
from __future__ import annotations

from typing import Any


def stop_status(stop: dict) -> str:
    if stop.get("picked_up"):
        return "picked_up"
    if stop.get("installed"):
        return "installed"
    if stop.get("skipped"):
        return "skipped"
    return "pending"


def stop_anchor(stop: dict) -> tuple[float, float] | None:
    """Best display coordinate: field GPS, then crossing, then midpoint."""
    fl, fo = stop.get("field_lat"), stop.get("field_lon")
    if fl is not None and fo is not None:
        return float(fl), float(fo)
    cl, co = stop.get("cross_lat"), stop.get("cross_lon")
    if cl is not None and co is not None:
        return float(cl), float(co)
    lat, lon = stop.get("lat"), stop.get("lon")
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    return None


def street_label(stop: dict) -> str:
    st = str(stop.get("street", "") or "").strip()
    if not st or st.lower() in ("nan", "none", "nat"):
        return f"Site {stop.get('id', '')}"
    return st


def first_pending_index(stops: list[dict]) -> int | None:
    for i, s in enumerate(stops):
        if not s.get("installed") and not s.get("skipped"):
            return i
    return None


def public_stop(stop: dict, *, seq: int | None = None) -> dict:
    """Lean, JSON-safe stop view for the phone map + list (no internal flags)."""
    anchor = stop_anchor(stop)
    out: dict[str, Any] = {
        "uid": stop.get("uid"),
        "id": stop.get("id"),
        "street": street_label(stop),
        "sheet": stop.get("sheet", ""),
        "status": stop_status(stop),
        "installed": bool(stop.get("installed")),
        "skipped": bool(stop.get("skipped")),
        "picked_up": bool(stop.get("picked_up")),
        "serial": str(stop.get("serial", "") or ""),
        "lanes": stop.get("lanes", 2),
        "direction": str(stop.get("direction", "") or ""),
        "notes": str(stop.get("notes", "") or ""),
        "begin_lat": stop.get("begin_lat"),
        "begin_lon": stop.get("begin_lon"),
        "end_lat": stop.get("end_lat"),
        "end_lon": stop.get("end_lon"),
        "cross_lat": stop.get("cross_lat"),
        "cross_lon": stop.get("cross_lon"),
        "cross_side": stop.get("cross_side"),
        "field_lat": stop.get("field_lat"),
        "field_lon": stop.get("field_lon"),
        "field_source": stop.get("field_coord_source"),
        "lat": stop.get("lat"),
        "lon": stop.get("lon"),
        "anchor": list(anchor) if anchor else None,
    }
    if seq is not None:
        out["seq"] = seq
    return out


def build_map_state(
    stops: list[dict],
    home: tuple[float, float] | list[float],
    route: dict | None,
    *,
    highlight_uid: str | None = None,
) -> dict:
    """Lean map payload for the mobile renderer.

    Mirrors the fields the existing `web/` MapLibre code reads, minus the
    desktop-only drive/pick/manual-grab machinery.
    """
    route = route or {}
    seq_stops = [public_stop(s, seq=i + 1) for i, s in enumerate(stops)]

    nxt_idx = first_pending_index(stops)
    auto_hi = stops[nxt_idx]["uid"] if nxt_idx is not None else None
    hi = highlight_uid or auto_hi

    polyline = route.get("polyline") or []
    return {
        "home": [float(home[0]), float(home[1])] if home else None,
        "stops": seq_stops,
        "route": {
            "polyline": polyline,
            "miles": float(route.get("miles") or 0.0),
            "graph": bool(route.get("graph")),
            # True after a manual reorder until the drive line is re-traced.
            "stale": bool(route.get("stale")),
        },
        "highlight_uid": hi,
        "counts": progress_counts(stops),
    }


def progress_counts(stops: list[dict]) -> dict:
    total = len(stops)
    installed = sum(1 for s in stops if s.get("installed"))
    skipped = sum(1 for s in stops if s.get("skipped"))
    picked = sum(1 for s in stops if s.get("picked_up"))
    pending = sum(
        1 for s in stops if not s.get("installed") and not s.get("skipped")
    )
    return {
        "total": total,
        "installed": installed,
        "skipped": skipped,
        "picked_up": picked,
        "pending": pending,
    }
