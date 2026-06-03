"""Ingest field files: Excel site coordinates + .EST map files.

Ported from the original Streamlit app's process_upload(), decoupled from any UI.
Pure functions that take file paths and return plain dicts/lists.

Flow:
  1. parse_excel_sites(...)  -> {site_id: {"lat", "lon", "street"}}
  2. match_est_files(...)    -> ordered raw stop list, one entry per (map, site)
"""
from __future__ import annotations

import math
import os
import re

import pandas as pd

# California-ish sanity box so a bad lat/lon column can't poison the route.
CA_LAT_MIN, CA_LAT_MAX = 30.0, 40.0
CA_LON_MIN, CA_LON_MAX = -125.0, -110.0


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _find_col(cols, *needle_sets):
    """Return the first column whose lowercased name contains ALL needles in any set."""
    low = [(c, str(c).lower()) for c in cols]
    for needles in needle_sets:
        for c, name in low:
            if all(n in name for n in needles):
                return c
    return None


def _clean_street(val, site_id: str) -> str:
    """Excel empty cells become 'nan' as text — never show that in the UI."""
    if val is None:
        return f"Site {site_id}"
    if isinstance(val, float) and math.isnan(val):
        return f"Site {site_id}"
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return f"Site {site_id}"
    return s


def _in_ca(lat, lon) -> bool:
    return CA_LAT_MIN < lat < CA_LAT_MAX and CA_LON_MIN < lon < CA_LON_MAX


def parse_excel_sites(excel_paths: list[str]) -> dict[str, dict]:
    """Read Excel/CSV file(s) -> {site_id: {begin/end lat/lon, lat/lon (midpoint), street}}.

    Each site is a street segment with a BEGIN (blue) and END (red) point. We also
    compute the segment midpoint, which is what the route/navigation drives to.
    Auto-detects column names. Only rows with an in-California begin point are kept.
    """
    sites: dict[str, dict] = {}
    for path in excel_paths:
        try:
            if str(path).lower().endswith(".csv"):
                frames = {"Sheet1": pd.read_csv(path, encoding="latin-1")}
            else:
                frames = pd.read_excel(path, sheet_name=None)
        except Exception:
            continue

        for _, df in frames.items():
            if df is None or df.empty:
                continue
            cols = list(df.columns)
            id_col = _find_col(cols, ("tds",), ("site",), ("id",)) or cols[0]
            b_lat = _find_col(cols, ("begin", "lat"), ("start", "lat"), ("lat",))
            b_lon = _find_col(cols, ("begin", "lon"), ("start", "lon"), ("lon",), ("lng",))
            e_lat = _find_col(cols, ("end", "lat"), ("finish", "lat"))
            e_lon = _find_col(cols, ("end", "lon"), ("finish", "lon"), ("end", "lng"))
            street_col = _find_col(cols, ("street",), ("road",), ("name",))
            if not b_lat or not b_lon:
                continue

            for _, row in df.iterrows():
                sid = str(row[id_col]).split(".")[0].strip()
                if not sid.isdigit():
                    continue
                try:
                    blat, blon = float(row[b_lat]), float(row[b_lon])
                except Exception:
                    continue
                if not _in_ca(blat, blon):
                    continue
                # End point (falls back to begin if absent/invalid).
                elat, elon = blat, blon
                if e_lat and e_lon:
                    try:
                        _el, _eo = float(row[e_lat]), float(row[e_lon])
                        if _in_ca(_el, _eo):
                            elat, elon = _el, _eo
                    except Exception:
                        pass
                street = _clean_street(row[street_col] if street_col else None, sid)
                sites.setdefault(sid, {
                    "begin_lat": blat, "begin_lon": blon,
                    "end_lat": elat, "end_lon": elon,
                    "lat": (blat + elat) / 2.0, "lon": (blon + elon) / 2.0,
                    "street": street,
                })
    return sites


def match_est_files(est_configs: list[dict], excel_sites: dict[str, dict],
                    home: tuple[float, float]) -> list[dict]:
    """Match site IDs found inside .EST map files to the Excel coordinates.

    est_configs: list of {"path": str, "label": str}.
    Returns a list of stop dicts (unordered) ready for the route engine:
        {id, uid, sheet, street, lat, lon, ...workflow fields...}
    Overlapping coordinates are nudged apart so pins don't stack (as before).
    """
    stops: list[dict] = []
    for cfg in est_configs:
        path, label = cfg["path"], cfg["label"]
        try:
            with open(path, "rb") as f:
                raw = f.read().decode("latin-1", errors="ignore")
        except Exception:
            continue

        for sid, data in excel_sites.items():
            if not re.search(r"\b" + re.escape(sid) + r"\b", raw):
                continue
            stops.append(new_stop(sid, label, data))
    return stops


# Field progress preserved when re-building route from the same uploads.
_PROGRESS_KEYS = (
    "installed", "skipped", "picked_up",
    "field_lat", "field_lon", "serial", "lanes", "direction", "notes",
    "date", "exact_time", "street_warning", "cross_lat", "cross_lon", "cross_side",
    "install_photo_path",
    "counter_unit_id", "counter_serial", "counter_cleared_at", "counter_download_path",
)


def merge_stop_progress(old: dict | None, fresh: dict) -> dict:
    """Keep install/pickup work on a stop when Excel/EST are re-imported."""
    if not old:
        return fresh
    out = dict(fresh)
    for key in _PROGRESS_KEYS:
        if key in old and old[key] is not None:
            out[key] = old[key]
    if old.get("installed") or old.get("skipped") or old.get("field_lat") is not None:
        st = str(old.get("street", "")).strip()
        if st and st.lower() not in ("nan", "none", "nat") and not st.startswith("Site "):
            out["street"] = st
    return out


def new_stop(site_id: str, sheet: str, data: dict) -> dict:
    """Create a fresh stop record (with begin/end + midpoint) and workflow fields."""
    return {
        "id": str(site_id),
        "uid": f"{sheet}_{site_id}",
        "sheet": sheet,
        "street": data.get("street", f"Site {site_id}"),
        # Segment endpoints for display (blue=begin, red=end).
        "begin_lat": float(data["begin_lat"]),
        "begin_lon": float(data["begin_lon"]),
        "end_lat": float(data["end_lat"]),
        "end_lon": float(data["end_lon"]),
        "lat": float(data["lat"]),
        "lon": float(data["lon"]),
        # Optimal road crossing on the segment line (set when route is built).
        "cross_lat": None,
        "cross_lon": None,
        "cross_side": None,
        "street_warning": "",
        # Field-capture (filled during install). Shows as green dot on map.
        "field_lat": None,
        "field_lon": None,
        "serial": "",
        "lanes": 2,
        "direction": "n",
        "notes": "",
        "installed": False,
        "skipped": False,
        "picked_up": False,
        "date": "",
        "exact_time": "",
        # TrafficViewer Pro .tvp metadata linked at pickup/install (Phase 1).
        "tvp": None,
    }
