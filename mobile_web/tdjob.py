"""Portable Traffic Deployer job file (.tdjob.json).

Phone and laptop can download this file and re-upload it later to pick up a
shift when the server is unreachable. It is a JSON snapshot of stops + route,
not a share-link token — restoring always creates a new job with a new token.
"""
from __future__ import annotations

import copy
import time
from typing import Any

FORMAT = "traffic-deployer-job"
VERSION = 1

# Fields copied from ingest.new_stop + field capture. Unknown keys are dropped
# so a crafted upload cannot inject huge blobs.
_STOP_KEYS = (
    "id",
    "uid",
    "sheet",
    "street",
    "begin_lat",
    "begin_lon",
    "end_lat",
    "end_lon",
    "lat",
    "lon",
    "cross_lat",
    "cross_lon",
    "cross_side",
    "street_warning",
    "field_lat",
    "field_lon",
    "field_coord_source",
    "field_accuracy_m",
    "serial",
    "lanes",
    "direction",
    "direction_source",
    "notes",
    "installed",
    "skipped",
    "picked_up",
    "date",
    "exact_time",
)


class TdjobError(ValueError):
    """Invalid or unsupported portable job file."""


def pack_job(job: dict) -> dict:
    """Build a token-free portable snapshot from a store job dict."""
    home = job.get("home")
    route = job.get("route") or {}
    return {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": time.time(),
        "source_job_id": str(job.get("id") or ""),
        "label": str(job.get("label") or "Field job"),
        "home": [float(home[0]), float(home[1])] if home and len(home) >= 2 else None,
        "home_label": str(job.get("home_label") or ""),
        "active_files": list(job.get("active_files") or []),
        "route": {
            "polyline": list(route.get("polyline") or []),
            "miles": float(route.get("miles") or 0.0),
            "graph": bool(route.get("graph")),
            "stale": bool(route.get("stale")),
        },
        "stops": [_sanitize_stop(s) for s in (job.get("stops") or [])],
    }


def unpack_job(payload: Any) -> dict:
    """Validate a portable file and return fields ready for JobStore.create.

    Returns {label, home, home_label, active_files, stops, route}.
    Raises TdjobError on bad input.
    """
    if not isinstance(payload, dict):
        raise TdjobError("Job file must be a JSON object.")
    fmt = str(payload.get("format") or "")
    if fmt != FORMAT:
        raise TdjobError("Not a Traffic Deployer job file.")
    try:
        ver = int(payload.get("version") or 0)
    except (TypeError, ValueError) as exc:
        raise TdjobError("Job file version is invalid.") from exc
    if ver != VERSION:
        raise TdjobError(f"Unsupported job file version {ver} (need {VERSION}).")

    raw_stops = payload.get("stops")
    if not isinstance(raw_stops, list) or not raw_stops:
        raise TdjobError("Job file has no stops.")
    stops = [_sanitize_stop(s) for s in raw_stops]
    if any(not s.get("uid") or not s.get("id") for s in stops):
        raise TdjobError("Every stop needs an id and uid.")

    home = payload.get("home")
    home_t = None
    if home is not None:
        try:
            home_t = (float(home[0]), float(home[1]))
        except (TypeError, ValueError, IndexError) as exc:
            raise TdjobError("Job file home coordinates are invalid.") from exc

    route = payload.get("route") if isinstance(payload.get("route"), dict) else {}
    return {
        "label": str(payload.get("label") or "Restored job")[:120],
        "home": home_t,
        "home_label": str(payload.get("home_label") or "")[:120],
        "active_files": [str(x)[:80] for x in (payload.get("active_files") or [])][:20],
        "stops": stops,
        "route": {
            "polyline": list(route.get("polyline") or []),
            "miles": float(route.get("miles") or 0.0),
            "graph": bool(route.get("graph")),
            "stale": bool(route.get("stale")),
        },
    }


def _sanitize_stop(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise TdjobError("Each stop must be an object.")
    out: dict[str, Any] = {}
    for key in _STOP_KEYS:
        if key not in raw:
            continue
        out[key] = copy.deepcopy(raw[key])
    if "uid" in out:
        out["uid"] = str(out["uid"])[:80]
    if "id" in out:
        out["id"] = str(out["id"])[:40]
    if "street" in out:
        out["street"] = str(out["street"] or "")[:300]
    if "notes" in out:
        out["notes"] = str(out["notes"] or "")[:300]
    if "serial" in out:
        out["serial"] = str(out["serial"] or "")[:80]
    if "direction" in out:
        out["direction"] = str(out["direction"] or "")[:8]
    if "lanes" in out:
        try:
            out["lanes"] = max(1, min(20, int(out["lanes"])))
        except (TypeError, ValueError):
            out["lanes"] = 2
    for flag in ("installed", "skipped", "picked_up"):
        if flag in out:
            out[flag] = bool(out[flag])
    # Phone map-state uses field_source; the store uses field_coord_source.
    if "field_coord_source" not in out and raw.get("field_source"):
        src = str(raw.get("field_source"))
        out["field_coord_source"] = src if src in ("phone_gps", "manual") else "phone_gps"
    return out
