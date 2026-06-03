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
    "CounterUnitID", "CounterSerial", "CounterCleared", "CounterDownload",
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
        "CounterUnitID": stop.get("counter_unit_id", ""),
        "CounterSerial": stop.get("counter_serial", ""),
        "CounterCleared": stop.get("counter_cleared_at", ""),
        "CounterDownload": stop.get("counter_download_path", ""),
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
            if s.get("counter_unit_id") and not str(s.get("counter_serial", "")).strip():
                missing.append(
                    f"Site {s.get('id')}: PicoCount configured but counter serial empty")
            if s.get("installed") and s.get("picked_up") and s.get("counter_unit_id"):
                if not str(s.get("counter_download_path", "")).strip():
                    missing.append(
                        f"Site {s.get('id')}: picked up but counter study not downloaded")
    return {"ok": not missing, "missing": missing, "count": len(done)}


def _excel_engines() -> list[str]:
    engines: list[str] = []
    try:
        import xlsxwriter  # noqa: F401

        engines.append("xlsxwriter")
    except ImportError:
        pass
    try:
        import openpyxl  # noqa: F401

        engines.append("openpyxl")
    except ImportError:
        pass
    return engines


def excel_engine_ok() -> tuple[bool, str]:
    """Whether Audit Excel export can run in this Python environment."""
    engines = _excel_engines()
    if not engines:
        return False, "Install dependencies via START.bat (xlsxwriter or openpyxl)."
    if "xlsxwriter" not in engines:
        return True, "Using openpyxl fallback (run START.bat for xlsxwriter)."
    return True, ""


def _write_workbook(df: pd.DataFrame, engine: str) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine=engine) as writer:
        df.drop(columns=["_Sheet"], errors="ignore")[_EXPORT_COLS].to_excel(
            writer, sheet_name="Master List", index=False)
        for sheet in df["_Sheet"].unique():
            safe = "".join(c for c in str(sheet) if c not in '[]:*?/\\')[:31] or "Map"
            sub = df[df["_Sheet"] == sheet].drop(columns=["_Sheet"], errors="ignore")
            sub[_EXPORT_COLS].to_excel(writer, sheet_name=safe, index=False)
    return out.getvalue()


def to_excel_result(stops: list[dict]) -> tuple[bytes | None, str | None]:
    """Build .xlsx bytes. Returns (data, error_message). error is None on success."""
    done = [s for s in stops if s.get("installed") or s.get("skipped")]
    if not done:
        return None, None
    engines = _excel_engines()
    if not engines:
        return None, (
            "Excel export is not available in this Python environment. "
            "Use START.bat or SMOKE.bat (project .venv), not bare python."
        )
    df = pd.DataFrame([_row(s) for s in done])
    last_err = ""
    for engine in engines:
        try:
            return _write_workbook(df, engine), None
        except ImportError as exc:
            last_err = str(exc)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
    return None, f"Excel export failed: {last_err or 'unknown error'}"


def to_excel_bytes(stops: list[dict]) -> bytes | None:
    """Build an .xlsx in memory. Returns None if nothing to export or on failure."""
    data, _err = to_excel_result(stops)
    return data


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
