"""Volume by Lane CSV — TrafficViewer Pro export layout."""
from __future__ import annotations

import csv
import io
import os
import re
from datetime import datetime, timedelta
from typing import Iterable

from core import picocount_hits

# TrafficViewer column order for 2-direction volume reports.
_CARDINALS_EW = ("East", "West")
_CARDINALS_NS = ("North", "South")

_AM_START = 6
_AM_END = 11
_PM_START = 15
_PM_END = 18


def _report_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/Los_Angeles"))
    except Exception:
        return datetime.now()


def direction_labels(
    *,
    primary: str = "",
    secondary: str = "",
    facing: str = "",
) -> tuple[str, str]:
    """
    Report column headers for the two travel directions.

    ``ab`` pairs map to primary; ``ba`` pairs map to secondary.
    Defaults: E/W when facing is e, else N/S.
    """
    primary = (primary or "").strip().title()
    secondary = (secondary or "").strip().title()
    if primary and secondary:
        return primary, secondary
    face = (facing or "e").strip().lower()[:1]
    if face == "e":
        return _CARDINALS_EW
    return _CARDINALS_NS


def facing_from_unit_id(unit_id: str) -> str:
    """Extract n/e facing letter from unit id like 15126ec1b."""
    m = re.search(r"([ne])c1b", (unit_id or "").lower())
    return m.group(1) if m else "e"


def labels_for_stop(stop: dict | None) -> tuple[str, str]:
    """Direction column names from stop metadata."""
    stop = stop or {}
    unit = str(stop.get("counter_unit_id") or stop.get("unit_id") or "")
    return direction_labels(
        primary=str(stop.get("volume_dir_primary") or ""),
        secondary=str(stop.get("volume_dir_secondary") or ""),
        facing=facing_from_unit_id(unit) or str(stop.get("direction") or "e"),
    )


def _fmt_dt(dt: datetime) -> str:
    """Windows-style datetime without leading zero on hour."""
    h = dt.strftime("%I").lstrip("0") or "12"
    return f"{dt.month}/{dt.day}/{dt.year} {h}:{dt.strftime('%M:%S %p')}"


def _fmt_day(dt: datetime) -> str:
    return dt.strftime("%A, %B %d, %Y")


def _fmt_hour(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _peak_label(hourly: dict[datetime, dict[str, int]], dirs: tuple[str, str]) -> str:
    """Highest total-flow hour in bucket (TrafficViewer PM/AM peak style)."""
    if not hourly:
        return ""
    best_h = max(hourly, key=lambda h: hourly[h]["total"])
    total = hourly[best_h]["total"]
    if total <= 0:
        return ""
    t = best_h.strftime("%H:%M:%S")
    return f"{total} (starting at {t})"


def _bin_hourly(
    events: list[dict],
    dir_primary: str,
    dir_secondary: str,
) -> dict[datetime, dict[str, int]]:
    buckets: dict[datetime, dict[str, int]] = {}
    for ev in events:
        ts: datetime = ev["datetime"]
        hour = ts.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(
            hour,
            {dir_primary: 0, dir_secondary: 0, "total": 0},
        )
        key = ev["direction_key"]
        col = dir_primary if key == "ab" else dir_secondary
        buckets[hour][col] += 1
        buckets[hour]["total"] += 1
    return buckets


def _day_hours(day: datetime.date, hourly: dict[datetime, dict[str, int]]) -> list[datetime]:
    hours = [h for h in hourly if h.date() == day]
    return sorted(hours)


def build_volume_report(
    path: str,
    *,
    unit_id: str = "",
    name: str = "",
    latitude: str = "Unknown",
    longitude: str = "Unknown",
    dir_primary: str = "",
    dir_secondary: str = "",
    facing: str = "",
    dwell_s: float = picocount_hits.DEFAULT_DWELL_S,
    pair_max_s: float = picocount_hits.DEFAULT_PAIR_MAX_S,
    cutoff: datetime | None = None,
    study_start: datetime | None = None,
) -> dict:
    """Parse study file and build Volume by Lane CSV text."""
    parsed = picocount_hits.parse_hits(path, study_start=study_start)
    if not parsed.get("ok"):
        return parsed

    d1, d2 = direction_labels(primary=dir_primary, secondary=dir_secondary, facing=facing)
    study_start: datetime = parsed["study_start"]
    events = picocount_hits.pair_vehicles(
        parsed["hits"],
        dwell_s=dwell_s,
        pair_max_s=pair_max_s,
        study_start=study_start,
    )
    if cutoff:
        events = [e for e in events if e["datetime"] <= cutoff]

    if not events:
        return {"ok": False, "error": "No vehicle events after pairing — study empty or too short."}

    started = events[0]["datetime"]
    ended = events[-1]["datetime"]
    hourly = _bin_hourly(events, d1, d2)

    report_name = (name or unit_id or os.path.splitext(os.path.basename(path))[0]).strip()
    lines: list[list[str]] = []
    blank = [""] * 8

    def row(*cells: str) -> None:
        lines.append(list(cells) + [""] * (8 - len(cells)))

    row("Volume by Lane")
    row("Name:", report_name)
    row("Latitude:", latitude, "", "Longitude:", longitude)
    row("Started:", _fmt_dt(started), "", "Ended:", _fmt_dt(ended))

    days = sorted({h.date() for h in hourly})
    grand = {d1: 0, d2: 0, "total": 0}
    all_hourly_vals: dict[str, list[int]] = {d1: [], d2: [], "total": []}

    for day in days:
        row(_fmt_day(datetime.combine(day, datetime.min.time())))
        row("Interval", "", d1, d2, "", "", "Total")
        day_tot = {d1: 0, d2: 0, "total": 0}
        am_hours = {h for h in _day_hours(day, hourly) if _AM_START <= h.hour <= _AM_END}
        pm_hours = {h for h in _day_hours(day, hourly) if _PM_START <= h.hour <= _PM_END}

        for hour in _day_hours(day, hourly):
            b = hourly[hour]
            row(
                _fmt_hour(hour),
                "",
                str(b[d1]),
                str(b[d2]),
                "",
                "",
                str(b["total"]),
            )
            for k in (d1, d2, "total"):
                day_tot[k] += b[k]
                grand[k] += b[k]
                all_hourly_vals[k].append(b[k])

        row("Daily Total", "", str(day_tot[d1]), str(day_tot[d2]), "", "", str(day_tot["total"]))
        am_peak = _peak_label({h: hourly[h] for h in am_hours}, (d1, d2))
        pm_peak = _peak_label({h: hourly[h] for h in pm_hours}, (d1, d2))
        row("AM Peak", "", am_peak if am_peak else "")
        row("PM Peak", "", pm_peak if pm_peak else "")

    def _avg(vals: list[int]) -> int:
        return round(sum(vals) / len(vals)) if vals else 0

    row(
        "Average Interval",
        "",
        str(_avg(all_hourly_vals[d1])),
        str(_avg(all_hourly_vals[d2])),
        "",
        "",
        str(_avg(all_hourly_vals["total"])),
    )
    row(
        "Maximum in one Interval",
        "",
        str(max(all_hourly_vals[d1]) if all_hourly_vals[d1] else 0),
        str(max(all_hourly_vals[d2]) if all_hourly_vals[d2] else 0),
        "",
        "",
        str(max(all_hourly_vals["total"]) if all_hourly_vals["total"] else 0),
    )
    row(
        "Grand Total",
        "",
        str(grand[d1]),
        str(grand[d2]),
        "",
        "",
        str(grand["total"]),
    )
    array_note = (
        "Array Type: Tube - Tube, \n"
        "Deadtime (in ms): 40, \n"
        "Maximum vehicle length: 110.0 ft, \n"
        "Maximum inter-axle spacing: 45.0 ft, \n"
        "Classification Scheme: FHWA-USA, \n"
        "Sensor Spacing: 3.0 ft, "
    )
    row(array_note)
    gen = _report_now().strftime("%A, %B %d, %Y %I:%M %p").replace(" 0", " ")
    row("", f"Report Generated {gen}", "", "", "", "", "", "1/1")

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for line in lines:
        writer.writerow(line)
    csv_text = buf.getvalue()

    return {
        "ok": True,
        "csv_text": csv_text,
        "unit_id": report_name,
        "started": started.isoformat(sep=" "),
        "ended": ended.isoformat(sep=" "),
        "vehicle_count": len(events),
        "directions": (d1, d2),
        "source_path": path,
        "hit_count": parsed["hit_count"],
        "study_start_source": parsed.get("study_start_source", ""),
    }


def default_export_path(data_dir: str, unit_id: str) -> str:
    """tds_data/exports/volume/<unit_id>_volume.csv"""
    safe = re.sub(r"[^\w.\-]+", "_", unit_id or "counter")
    folder = os.path.join(data_dir, "exports", "volume")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{safe}_volume.csv")


def write_volume_csv(
    path: str,
    dest: str,
    *,
    stop: dict | None = None,
    **kwargs,
) -> dict:
    """Build report from study file and write CSV to dest."""
    stop = stop or {}
    unit = str(
        kwargs.pop("unit_id", None)
        or stop.get("counter_unit_id")
        or os.path.splitext(os.path.basename(path))[0]
    )
    d1, d2 = labels_for_stop(stop)
    lat = stop.get("field_lat") or stop.get("lat")
    lon = stop.get("field_lon") or stop.get("lon")
    cleared = picocount_hits._parse_wall_time(str(stop.get("counter_cleared_at") or ""))
    result = build_volume_report(
        path,
        unit_id=unit,
        name=unit,
        latitude=str(lat) if lat not in (None, "") else "Unknown",
        longitude=str(lon) if lon not in (None, "") else "Unknown",
        dir_primary=str(kwargs.pop("dir_primary", None) or d1),
        dir_secondary=str(kwargs.pop("dir_secondary", None) or d2),
        study_start=kwargs.pop("study_start", None) or cleared,
        **kwargs,
    )
    if not result.get("ok"):
        return result
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="") as f:
        f.write(result["csv_text"])
    result["path"] = os.path.abspath(dest)
    return result


def volume_reports_for_stops(stops: list[dict], data_dir: str) -> list[dict]:
    """Generate volume CSV for every picked-up stop with a counter download."""
    out: list[dict] = []
    for s in stops:
        dl = str(s.get("counter_download_path") or "").strip()
        if not dl or not os.path.isfile(dl):
            continue
        unit = str(s.get("counter_unit_id") or f"site_{s.get('id', 'x')}")
        dest = default_export_path(data_dir, unit)
        res = write_volume_csv(dl, dest, stop=s)
        res["site_id"] = s.get("id")
        out.append(res)
    return out
