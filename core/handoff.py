"""Shift handoff: IG TFC Excel + Map 1/2 *_FIELD.est with clean filenames."""
from __future__ import annotations

import os
import re
from datetime import date

from core import export
from core.est_field_gps import (
    apply_field_gps_to_est,
    field_coords_from_stops,
    report_shared_coord_conflicts,
)
from core.est_viewer import write_viewer_files


def handoff_prefix(
    *,
    ig_tfc_path: str = "",
    est_paths: list[str] | None = None,
    explicit: str = "",
) -> str:
    """Human label for handoff files, e.g. 'Week 14'."""
    if explicit and explicit.strip():
        return explicit.strip()
    for src in [ig_tfc_path, *(est_paths or [])]:
        base = os.path.splitext(os.path.basename(str(src)))[0]
        m = re.search(r"week\s*(\d+)", base, re.I)
        if m:
            return f"Week {m.group(1)}"
    return "Field"


def handoff_dir(data_dir: str) -> str:
    """tds_data/exports/shift_handoff/ — fixed folder to zip for the office."""
    path = os.path.join(export.export_dir(data_dir), "shift_handoff")
    os.makedirs(path, exist_ok=True)
    return path


def handoff_filenames(prefix: str, map_count: int) -> dict[str, str]:
    """Return display names: excel, map1..mapN, readme."""
    names: dict[str, str] = {
        "excel": f"{prefix} IG TFC.xlsx",
        "readme": "HANDOFF_README.txt",
    }
    for i in range(1, max(1, map_count) + 1):
        names[f"map{i}"] = f"{prefix} Map {i}.est"
    return names


def _normalize_sheet_name(name: str) -> str:
    """Match 'Week 14 Day 1 Isaac (1).est' to stop sheet 'Week 14 Day 1 Isaac'."""
    name = str(name or "").strip()
    return re.sub(r"\s*\(\d+\)\s*$", "", name)


def _est_sheet_label(est_path: str) -> str:
    return _normalize_sheet_name(os.path.splitext(os.path.basename(est_path))[0])


def _stops_for_sheet(stops: list[dict], sheet: str) -> list[dict]:
    want = _normalize_sheet_name(sheet)
    return [
        s for s in stops
        if _normalize_sheet_name(str(s.get("sheet", ""))) == want
    ]


def _installed_missing_gps(stops: list[dict]) -> list[str]:
    out: list[str] = []
    for s in stops:
        if not s.get("installed"):
            continue
        if s.get("field_lat") is None or s.get("field_lon") is None:
            out.append(f"Site {s.get('id')} ({s.get('sheet', '?')})")
    return out


def _write_readme(
    path: str,
    *,
    prefix: str,
    excel_name: str,
    map_names: list[str],
    no_gps: list[str],
    conflict_lines: list[str],
) -> None:
    lines = [
        f"{prefix} install handoff — Traffic Deployer field GPS",
        f"Built: {date.today().isoformat()}",
        "",
        "Send these files:",
        f"  1. {excel_name}  — install log (serials, skipped, GPS on installed only)",
    ]
    for i, name in enumerate(map_names, start=2):
        lines.append(f"  {i}. {name}  — Map {i - 1} field install pins")
    lines.extend([
        "",
        "Open the Map *.est files in Streets & Trips — or open the matching .html in any browser.",
        "Universal viewers: .html (double-click) or .kml (Google Earth). No Streets & Trips needed for those.",
        "Skipped sites: no field GPS pin — blue/red begin/end from Week 14 Excel only.",
        "Installed sites: green field GPS pin (Grab GPS) on Map *.est and in the .html viewer.",
        "",
        "Excel LAT/LON columns match the Map *.est pushpin locations.",
    ])
    if no_gps:
        lines.extend(["", "NOTE — installed but no field GPS captured:"])
        lines.extend(f"  - {x}" for x in no_gps)
    if conflict_lines:
        lines.extend([
            "",
            "NOTE — Streets & Trips shares one lat/lon slot between some site pairs.",
            "Excel LAT/LON is always correct. If a pin looks wrong in EST, use Excel or",
            "nudge the pushpin once in Streets & Trips for these pairs:",
        ])
        lines.extend(f"  - {x}" for x in conflict_lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def export_shift_handoff(
    stops: list[dict],
    est_paths: list[str],
    *,
    data_dir: str,
    ig_tfc_path: str = "",
    prefix: str = "",
    out_dir: str = "",
) -> dict:
    """Write IG TFC Excel + Map 1/2 .est to shift_handoff folder. Returns summary dict."""
    est_paths = [p for p in est_paths if p and os.path.isfile(p)]
    folder = out_dir or handoff_dir(data_dir)
    os.makedirs(folder, exist_ok=True)
    label = handoff_prefix(ig_tfc_path=ig_tfc_path, est_paths=est_paths, explicit=prefix)
    names = handoff_filenames(label, len(est_paths) or 2)

    result: dict = {
        "ok": False,
        "prefix": label,
        "folder": folder,
        "files": {},
        "errors": [],
        "warnings": [],
        "est_results": [],
    }

    done = [s for s in stops if s.get("installed") or s.get("skipped")]
    if not done:
        result["errors"].append("Nothing to export yet (no installed/skipped sites).")
        return result

    xlsx_bytes, xlsx_err = export.to_excel_result(
        stops, ig_tfc_path=ig_tfc_path, data_dir=data_dir,
    )
    if not xlsx_bytes:
        result["errors"].append(xlsx_err or "Excel export failed.")
        return result

    excel_path = os.path.join(folder, names["excel"])
    with open(excel_path, "wb") as f:
        f.write(xlsx_bytes)
    result["files"]["excel"] = excel_path

    no_gps = _installed_missing_gps(stops)
    if no_gps:
        result["warnings"].extend(f"No field GPS: {x}" for x in no_gps)

    map_names: list[str] = []
    conflict_lines: list[str] = []
    if not est_paths:
        result["warnings"].append("No .est maps loaded — Excel only.")
    else:
        for i, est_path in enumerate(est_paths, start=1):
            map_key = f"map{i}"
            map_name = names.get(map_key, f"{label} Map {i}.est")
            map_names.append(map_name)
            sheet = _est_sheet_label(est_path)
            sheet_stops = _stops_for_sheet(stops, sheet)
            report_sheet = str(sheet_stops[0].get("sheet", "")).strip() if sheet_stops else sheet
            if not sheet_stops:
                result["warnings"].append(
                    f"{map_name}: no stops for sheet {sheet!r} — check .est filename vs route sheets.",
                )
            coords = field_coords_from_stops(
                sheet_stops, field_only=True, installed_only=True,
            )
            out_est = os.path.join(folder, map_name)
            try:
                est_result = apply_field_gps_to_est(est_path, coords, out_est)
                result["est_results"].append(est_result)
                result["files"][map_key] = out_est
                try:
                    viewers = write_viewer_files(
                        out_est,
                        base_path=os.path.splitext(out_est)[0],
                        title=map_name,
                        stops=sheet_stops,
                    )
                    result["files"][f"{map_key}_html"] = viewers["html"]
                    result["files"][f"{map_key}_kml"] = viewers["kml"]
                except Exception as exc:  # noqa: BLE001
                    result["warnings"].append(f"{map_name} viewer: {exc}")
                if est_result.get("missing_in_est"):
                    result["warnings"].append(
                        f"{map_name}: not in EST — {', '.join(est_result['missing_in_est'])}",
                    )
                if est_result.get("warnings"):
                    result["warnings"].extend(
                        [f"{map_name}: {w}" for w in est_result["warnings"]],
                    )
                try:
                    for line in report_shared_coord_conflicts(
                        est_path, excel_path, report_sheet,
                    ):
                        conflict_lines.append(f"{report_sheet}: {line}")
                except ValueError:
                    pass
            except Exception as exc:  # noqa: BLE001
                result["errors"].append(f"{map_name}: {exc}")

    readme_path = os.path.join(folder, names["readme"])
    _write_readme(
        readme_path,
        prefix=label,
        excel_name=names["excel"],
        map_names=map_names,
        no_gps=no_gps,
        conflict_lines=conflict_lines,
    )
    result["files"]["readme"] = readme_path

    result["ok"] = bool(result["files"].get("excel")) and not result["errors"]
    return result
