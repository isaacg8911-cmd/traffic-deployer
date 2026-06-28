"""End-of-day export: build the IG TFC Excel workbook (CSV fallback).

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


def to_excel_result(
    stops: list[dict],
    *,
    ig_tfc_path: str = "",
    data_dir: str = "",
) -> tuple[bytes | None, str | None]:
    """IG TFC Excel: sheet layout + LAT/LON on installed sites."""
    if not stops:
        return None, None
    if not _excel_engines():
        return None, (
            "Excel export is not available in this Python environment. "
            "Use START.bat or SMOKE.bat (project .venv), not bare python."
        )
    template = resolve_ig_tfc_template(ig_tfc_path=ig_tfc_path, data_dir=data_dir)
    try:
        data = _write_ig_tfc_workbook(stops, template_path=template)
        if data:
            return data, None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    return None, "Nothing to export."


def to_excel_bytes(
    stops: list[dict],
    *,
    ig_tfc_path: str = "",
    data_dir: str = "",
) -> bytes | None:
    """Build an .xlsx in memory. Returns None if nothing to export or on failure."""
    data, _err = to_excel_result(stops, ig_tfc_path=ig_tfc_path, data_dir=data_dir)
    return data


def to_csv_text(
    stops: list[dict],
    *,
    ig_tfc_path: str = "",
    data_dir: str = "",
) -> str:
    return to_ig_tfc_csv_text(stops)


def export_dir(data_dir: str) -> str:
    """Default folder for end-of-day reports (created on demand)."""
    path = os.path.join(data_dir, "exports")
    os.makedirs(path, exist_ok=True)
    return path


def _safe_profile(profile: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", (profile or "DEFAULT").strip().upper())
    return (s[:24] or "DEFAULT")


def default_report_path(data_dir: str, profile: str, ext: str) -> str:
    """tds_data/exports/IG_TFC_GPS_<PROFILE>_<YYYY-MM-DD>.<ext>"""
    date, _ = ca_now()
    name = f"IG_TFC_GPS_{_safe_profile(profile)}_{date}.{ext.lstrip('.')}"
    return os.path.join(export_dir(data_dir), name)


# ------------------------------------------------------------------ IG TFC export (template + field GPS)


def resolve_ig_tfc_template(
    *,
    ig_tfc_path: str = "",
    data_dir: str = "",
) -> str | None:
    """Find the IG TFC workbook used as the report template."""
    candidates = [
        ig_tfc_path,
        os.environ.get("TD_WEEK14_IG_TFC", ""),
        os.path.join(data_dir, "week_14_ig_tfc.xlsx") if data_dir else "",
        r"c:\Users\isaac\Downloads\week 14 ig tfc.xlsx",
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _find_col(cols, *needles: str) -> str | None:
    for col in cols:
        name = str(col).lower().replace("#", "").strip()
        if any(n in name for n in needles):
            return col
    return None


def _site_id_from_cell(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).split(".")[0].strip()


def _flag_cell(on: bool) -> str:
    return "x" if on else ""


def _gps_pair(stop: dict) -> tuple[float | None, float | None]:
    if not stop.get("installed"):
        return None, None
    lat, lon = stop.get("field_lat"), stop.get("field_lon")
    if lat is None or lon is None:
        return None, None
    return round(float(lat), 6), round(float(lon), 6)


def _stops_by_id(stops: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for s in stops:
        sid = _site_id_from_cell(s.get("id"))
        if sid:
            out[sid] = s
    return out


def _merge_stop_into_ig_row(df: pd.DataFrame, idx: int, stop: dict) -> None:
    cols = list(df.columns)
    serial_col = _find_col(cols, "serial")
    dir_col = _find_col(cols, "direction")
    lanes_col = _find_col(cols, "lane")
    notes_col = next(
        (c for c in cols if str(c).lower().strip() in ("notes", "note")),
        _find_col(cols, "note"),
    )
    inst_col = _find_col(cols, "installed")
    skip_col = _find_col(cols, "skipped")
    pick_col = _find_col(cols, "picked")

    serial = str(stop.get("serial") or stop.get("counter_serial") or "").strip()
    if serial.lower() in ("nan", "none", "nat"):
        serial = ""
    if serial_col and serial:
        try:
            num = float(serial)
            df.at[idx, serial_col] = num
        except ValueError:
            df.at[idx, serial_col] = serial
    direction = str(stop.get("direction") or "").strip()
    if dir_col and direction and direction.lower() not in ("nan", "none"):
        df.at[idx, dir_col] = direction
    if lanes_col and stop.get("lanes") is not None:
        try:
            df.at[idx, lanes_col] = int(stop.get("lanes") or 2)
        except (TypeError, ValueError):
            pass
    if notes_col:
        notes = str(stop.get("notes") or "").strip()
        if notes and notes.lower() not in ("nan", "none", "nat"):
            df.at[idx, notes_col] = notes
    if inst_col:
        df.at[idx, inst_col] = _flag_cell(bool(stop.get("installed")))
    if skip_col:
        df.at[idx, skip_col] = _flag_cell(bool(stop.get("skipped")))
    if pick_col:
        df.at[idx, pick_col] = _flag_cell(bool(stop.get("picked_up")))

    lat, lon = _gps_pair(stop)
    if "LAT" not in df.columns:
        df["LAT"] = pd.NA
    if "LON" not in df.columns:
        df["LON"] = pd.NA
    df.at[idx, "LAT"] = lat
    df.at[idx, "LON"] = lon


def _ig_row_from_stop(stop: dict) -> dict:
    lat, lon = _gps_pair(stop)
    return {
        "Date": stop.get("date", ""),
        "Site": stop.get("id", ""),
        "Serial": stop.get("serial") or stop.get("counter_serial") or "",
        "Directions": stop.get("direction", ""),
        "Lanes": stop.get("lanes", 2),
        "Notes": stop.get("notes", ""),
        "Installed": _flag_cell(bool(stop.get("installed"))),
        "Skipped": _flag_cell(bool(stop.get("skipped"))),
        "Picked up": _flag_cell(bool(stop.get("picked_up"))),
        "LAT": lat,
        "LON": lon,
    }


_IG_TFC_FALLBACK_COLS = [
    "Date", "Site", "Serial", "Directions", "Lanes", "Notes",
    "Installed", "Skipped", "Picked up", "LAT", "LON",
]


def _write_ig_tfc_workbook(
    stops: list[dict],
    *,
    template_path: str | None = None,
) -> bytes | None:
    by_id = _stops_by_id(stops)
    engines = _excel_engines()
    if not engines:
        return None

    sheets: dict[str, pd.DataFrame] = {}
    if template_path and os.path.isfile(template_path):
        try:
            frames = pd.read_excel(template_path, sheet_name=None)
        except Exception:
            frames = {}
        for sheet_name, df in frames.items():
            if df is None or df.empty:
                continue
            out = df.copy()
            site_col = _find_col(out.columns, "site")
            if site_col:
                for idx, row in out.iterrows():
                    sid = _site_id_from_cell(row.get(site_col))
                    stop = by_id.get(sid)
                    if stop:
                        _merge_stop_into_ig_row(out, idx, stop)
            sheets[str(sheet_name)] = out

    if not sheets:
        by_sheet: dict[str, list[dict]] = {}
        for s in stops:
            sheet = str(s.get("sheet") or "Map")
            by_sheet.setdefault(sheet, []).append(s)
        for sheet_name, sheet_stops in by_sheet.items():
            sheets[sheet_name] = pd.DataFrame(
                [_ig_row_from_stop(s) for s in sheet_stops], columns=_IG_TFC_FALLBACK_COLS)

    if not sheets:
        return None

    last_err = ""
    for engine in engines:
        try:
            out_io = io.BytesIO()
            with pd.ExcelWriter(out_io, engine=engine) as writer:
                for sheet_name, df in sheets.items():
                    safe = "".join(c for c in str(sheet_name) if c not in '[]:*?/\\')[:31] or "Map"
                    df.to_excel(writer, sheet_name=safe, index=False)
            return out_io.getvalue()
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
    raise RuntimeError(last_err or "IG TFC export failed")


def to_ig_tfc_csv_text(stops: list[dict]) -> str:
    """Flat CSV in IG TFC column order (+ MapDay when multiple sheets)."""
    by_sheet: dict[str, list[dict]] = {}
    for s in stops:
        if not (s.get("installed") or s.get("skipped")):
            continue
        sheet = str(s.get("sheet") or "Map")
        by_sheet.setdefault(sheet, []).append(s)
    rows: list[dict] = []
    multi = len(by_sheet) > 1
    for sheet_name, sheet_stops in by_sheet.items():
        for s in sheet_stops:
            row = _ig_row_from_stop(s)
            if multi:
                row = {"MapDay": sheet_name, **row}
            rows.append(row)
    if not rows:
        return ""
    df = pd.DataFrame(rows)
    cols = (["MapDay"] if multi else []) + _IG_TFC_FALLBACK_COLS
    return df[cols].to_csv(index=False)


def to_audit_excel_result(stops: list[dict]) -> tuple[bytes | None, str | None]:
    """Legacy wide audit workbook (Master List + counter columns)."""
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


def to_audit_csv_text(stops: list[dict]) -> str:
    done = [s for s in stops if s.get("installed") or s.get("skipped")]
    df = pd.DataFrame([_row(s) for s in done]).drop(columns=["_Sheet"], errors="ignore")
    if not df.empty:
        df = df[_EXPORT_COLS]
    return df.to_csv(index=False)


def _flag(val) -> bool:
    return str(val or "").strip().lower() in ("x", "true", "1", "yes")


def _float_or_none(val) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def stop_from_report_row(row: dict, sheet: str) -> dict | None:
    """Reverse of _row — one TDS_Report row -> stop dict for maps_links."""
    site = str(row.get("Site", "")).split(".")[0].strip()
    if not site:
        return None
    lat = _float_or_none(row.get("LAT"))
    lon = _float_or_none(row.get("LON"))
    cross_lat = _float_or_none(row.get("CrossLAT"))
    cross_lon = _float_or_none(row.get("CrossLON"))
    street = str(row.get("Street", "") or "").strip()
    if not street or street.lower() in ("nan", "none", "nat"):
        street = f"Site {site}"
    lanes = row.get("Lanes")
    try:
        lanes_i = int(lanes) if lanes is not None and not pd.isna(lanes) else 2
    except (TypeError, ValueError):
        lanes_i = 2
    return {
        "id": site,
        "uid": f"{sheet}_{site}",
        "sheet": sheet,
        "street": street,
        "lat": lat,
        "lon": lon,
        "cross_lat": cross_lat,
        "cross_lon": cross_lon,
        "field_lat": lat,
        "field_lon": lon,
        "serial": str(row.get("Serial", "") or "").strip(),
        "lanes": lanes_i,
        "direction": str(row.get("Directions", "") or "").strip(),
        "notes": str(row.get("Notes", "") or "").strip(),
        "street_warning": str(row.get("WideStreet", "") or "").strip(),
        "counter_unit_id": str(row.get("CounterUnitID", "") or "").strip(),
        "counter_serial": str(row.get("CounterSerial", "") or "").strip(),
        "counter_cleared_at": str(row.get("CounterCleared", "") or "").strip(),
        "counter_download_path": str(row.get("CounterDownload", "") or "").strip(),
        "installed": _flag(row.get("Installed")),
        "skipped": _flag(row.get("Skipped")),
        "picked_up": _flag(row.get("Picked up")),
        "date": str(row.get("Date", "") or "").strip(),
        "exact_time": str(row.get("ExactTime", "") or "").strip(),
    }


def _ig_tfc_site_id(row: dict) -> str:
    for key, val in row.items():
        if "site" in str(key).lower():
            sid = str(val or "").split(".")[0].strip()
            if sid.isdigit():
                return sid
    return ""


def _ig_tfc_val(row: dict, *name_parts: str) -> str:
    parts = [p.lower() for p in name_parts]
    for key, val in row.items():
        name = str(key).lower()
        if all(p in name for p in parts):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return ""
            return str(val).strip()
    return ""


def stop_from_ig_tfc_row(row: dict, sheet: str) -> dict | None:
    """One IG TFC row (Installed / Skipped / Picked up columns) -> stop progress dict."""
    site = _ig_tfc_site_id(row)
    if not site:
        return None
    lanes = row.get("Lanes")
    try:
        lanes_i = int(lanes) if lanes is not None and not pd.isna(lanes) else 2
    except (TypeError, ValueError):
        lanes_i = 2
    direction = _ig_tfc_val(row, "direction") or _ig_tfc_val(row, "directions")
    serial = _ig_tfc_val(row, "serial")
    notes = _ig_tfc_val(row, "notes")
    return {
        "id": site,
        "uid": f"{sheet}_{site}",
        "sheet": sheet,
        "serial": serial,
        "lanes": lanes_i,
        "direction": direction,
        "notes": notes,
        "installed": _flag(row.get("Installed")),
        "skipped": _flag(row.get("Skipped")),
        "picked_up": _flag(row.get("Picked up")),
    }


def parse_ig_tfc_workbook(path: str) -> dict[str, list[dict]]:
    """Read week IG TFC .xlsx -> {sheet_name: [stop dicts with install flags only]}."""
    if not os.path.isfile(path):
        return {}
    try:
        frames = pd.read_excel(path, sheet_name=None)
    except Exception:
        return {}
    out: dict[str, list[dict]] = {}
    for sheet, df in frames.items():
        if df is None or df.empty:
            continue
        stops: list[dict] = []
        for row in df.to_dict(orient="records"):
            stop = stop_from_ig_tfc_row(row, str(sheet))
            if stop:
                stops.append(stop)
        if stops:
            out[str(sheet)] = stops
    return out


_IG_TFC_PROGRESS_KEYS = (
    "installed", "skipped", "picked_up", "serial", "lanes", "direction", "notes",
)


def apply_ig_tfc_progress(stops: list[dict], path: str) -> list[dict]:
    """IG TFC workbook is install truth; field GPS kept only on installed stops."""
    sheets = parse_ig_tfc_workbook(path)
    by_uid = {s["uid"]: s for slist in sheets.values() for s in slist}
    out: list[dict] = []
    for st in stops:
        s = dict(st)
        ig = by_uid.get(s["uid"])
        if ig:
            for key in _IG_TFC_PROGRESS_KEYS:
                if key in ig:
                    s[key] = ig[key]
        else:
            s["installed"] = False
            s["skipped"] = False
            s["picked_up"] = False
        if not s.get("installed"):
            s["field_lat"] = None
            s["field_lon"] = None
        out.append(s)
    return out


def parse_report_workbook(
    path: str,
    *,
    skip_master: bool = True,
) -> dict[str, list[dict]]:
    """Read TDS_Report .xlsx -> {sheet_name: [stop dicts]}."""
    if not os.path.isfile(path):
        return {}
    try:
        frames = pd.read_excel(path, sheet_name=None)
    except Exception:
        return {}
    out: dict[str, list[dict]] = {}
    for sheet, df in frames.items():
        if skip_master and str(sheet).strip().lower() == "master list":
            continue
        if df is None or df.empty:
            continue
        stops: list[dict] = []
        for row in df.to_dict(orient="records"):
            stop = stop_from_report_row(row, str(sheet))
            if stop:
                stops.append(stop)
        if stops:
            out[str(sheet)] = stops
    return out
