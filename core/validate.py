"""Pre-flight checks before BUILD OPTIMIZED ROUTE."""
from __future__ import annotations

import os
from collections import Counter

from core.home_check import check_home_vs_stops


def validate_build(
    excel_paths: list[str],
    est_configs: list[dict],
    sites: dict,
    stops: list[dict],
    home: tuple[float, float] | None = None,
    default_home: tuple[float, float] | None = None,
) -> dict:
    """Return {ok, errors[], warnings[], stats{}}."""
    errors: list[str] = []
    warnings: list[str] = []

    if not excel_paths:
        errors.append("Add at least one Excel/CSV file with site coordinates.")
    if not est_configs:
        errors.append("Add at least one .EST map file.")

    for p in excel_paths:
        if not os.path.isfile(p):
            errors.append(f"Excel file not found: {p}")
    for cfg in est_configs:
        p = cfg.get("path", "")
        if p and not os.path.isfile(p):
            errors.append(f"EST file not found: {p}")

    if excel_paths and not sites:
        errors.append(
            "No sites parsed from Excel. Check begin lat/lon columns and California coordinates.")

    if sites and est_configs and not stops:
        errors.append(
            "0 sites matched .EST maps. Site IDs in Excel must appear inside the .EST file text.")

    ids = [str(s.get("id", "")) for s in stops]
    dupes = [sid for sid, n in Counter(ids).items() if n > 1]
    if dupes:
        sample = ", ".join(dupes[:8])
        more = f" (+{len(dupes) - 8} more)" if len(dupes) > 8 else ""
        warnings.append(
            f"Duplicate site IDs across maps ({len(dupes)}): {sample}{more}. "
            "Each map/day creates its own stop — confirm that is intended.")

    missing_street = sum(
        1 for s in stops
        if str(s.get("street", "")).strip().lower() in ("", "nan", "none")
        or str(s.get("street", "")).startswith("Site ")
    )
    if missing_street and stops:
        warnings.append(f"{missing_street} stop(s) have no street name in Excel (will show as Site #).")

    if home is not None and stops:
        warnings.extend(check_home_vs_stops(home, stops, default_home=default_home))

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "excel_files": len(excel_paths),
            "est_files": len(est_configs),
            "sites_in_excel": len(sites),
            "stops_matched": len(stops),
        },
    }
