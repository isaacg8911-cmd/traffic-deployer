"""End-of-day export: build the boss-facing Excel workbook (CSV fallback).

Ported from the original app's audit tab. Produces a Master List sheet plus one
sheet per map/day.
"""
from __future__ import annotations

import io
import os
import re

import pandas as pd

from core.state import ca_now

# Column order presented to the office.
_EXPORT_COLS = [
    "Date", "ExactTime", "MapDay", "Site", "Street", "Serial", "Directions", "Lanes",
    "Notes", "WideStreet", "CrossLAT", "CrossLON", "LAT", "LON",
    "Installed", "Skipped", "Picked up",
]


def _row(stop: dict) -> dict:
    lat = stop.get("field_lat") or stop.get("lat")
    lon = stop.get("field_lon") or stop.get("lon")
    return {
        "Date": stop.get("date", ""),
        "ExactTime": stop.get("exact_time", ""),
        "MapDay": stop.get("sheet", ""),
        "Site": stop.get("id", ""),
        "Street": stop.get("street", ""),
        "Serial": stop.get("serial", ""),
        "Directions": stop.get("direction", ""),
        "Lanes": stop.get("lanes", ""),
        "Notes": stop.get("notes", ""),
        "WideStreet": stop.get("street_warning", ""),
        "CrossLAT": stop.get("cross_lat"),
        "CrossLON": stop.get("cross_lon"),
        "LAT": lat,
        "LON": lon,
        "Installed": "x" if stop.get("installed") else "",
        "Skipped": "x" if stop.get("skipped") else "",
        "Picked up": "x" if stop.get("picked_up") else "",
        "_Sheet": stop.get("sheet", "Map"),
    }


def audit(stops: list[dict]) -> dict:
    """Return {ok, missing:[...], count} for completed (installed/skipped) sites."""
    done = [s for s in stops if s.get("installed") or s.get("skipped")]
    missing = []
    for s in done:
        if s.get("installed"):
            if not str(s.get("serial", "")).strip():
                missing.append(f"Site {s.get('id')}: missing Serial #")
            street = str(s.get("street", "")).strip()
            if not street or street.lower() == "nan":
                missing.append(f"Site {s.get('id')}: missing Street name")
    return {"ok": not missing, "missing": missing, "count": len(done)}


def to_excel_bytes(stops: list[dict]) -> bytes | None:
    """Build an .xlsx in memory. Returns None if the Excel engine is unavailable."""
    done = [s for s in stops if s.get("installed") or s.get("skipped")]
    if not done:
        return None
    df = pd.DataFrame([_row(s) for s in done])
    try:
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
            df.drop(columns=["_Sheet"], errors="ignore")[_EXPORT_COLS].to_excel(
                writer, sheet_name="Master List", index=False)
            for sheet in df["_Sheet"].unique():
                safe = "".join(c for c in str(sheet) if c not in '[]:*?/\\')[:31] or "Map"
                sub = df[df["_Sheet"] == sheet].drop(columns=["_Sheet"], errors="ignore")
                sub[_EXPORT_COLS].to_excel(writer, sheet_name=safe, index=False)
        return out.getvalue()
    except Exception:
        return None


def to_csv_text(stops: list[dict]) -> str:
    done = [s for s in stops if s.get("installed") or s.get("skipped")]
    df = pd.DataFrame([_row(s) for s in done]).drop(columns=["_Sheet"], errors="ignore")
    if not df.empty:
        df = df[_EXPORT_COLS]
    return df.to_csv(index=False)


def export_dir(data_dir: str) -> str:
    """Default folder for end-of-day reports (created on demand)."""
    path = os.path.join(data_dir, "exports")
    os.makedirs(path, exist_ok=True)
    return path


def _safe_profile(profile: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", (profile or "DEFAULT").strip().upper())
    return (s[:24] or "DEFAULT")


def default_report_path(data_dir: str, profile: str, ext: str) -> str:
    """tds_data/exports/TDS_Report_<PROFILE>_<YYYY-MM-DD>.<ext>"""
    date, _ = ca_now()
    name = f"TDS_Report_{_safe_profile(profile)}_{date}.{ext.lstrip('.')}"
    return os.path.join(export_dir(data_dir), name)
