"""Resolve job files for ship-gate field tests — bundled validation default, director override via env."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Shipped with the app for desk proof when director job files are not on this PC.
# (Folder name demo_data is legacy on disk — not "demo mode", just bundled test job files.)
BUNDLED_XLS = os.path.join(ROOT, "demo_data", "demo_sites.csv")
BUNDLED_ESTS = [(os.path.join(ROOT, "demo_data", "DemoDay.EST"), "Day 1")]
# Non-factory coords (factory default 33.7715, -117.9431 fails checklist).
BUNDLED_HOME = (33.8123, -117.9234)
BUNDLED_HOME_LABEL = "Validation start (desk proof)"


@dataclass(frozen=True)
class FieldJobFixture:
    label: str
    xls: str
    ests: tuple[tuple[str, str], ...]  # (path, label)
    home: tuple[float, float]
    home_label: str
    source: str  # "bundled" | "env" | "manifest"


def _parse_est_list(raw: str) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    for i, chunk in enumerate(raw.split(";")):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "|" in chunk:
            path, label = chunk.split("|", 1)
            out.append((path.strip(), label.strip()))
        else:
            out.append((chunk, f"Day {i + 1}"))
    return tuple(out)


def _home_from_env() -> tuple[tuple[float, float], str]:
    lat = os.environ.get("TD_JOB_HOME_LAT", "").strip()
    lon = os.environ.get("TD_JOB_HOME_LON", "").strip()
    if lat and lon:
        try:
            return (float(lat), float(lon)), os.environ.get("TD_JOB_HOME_LABEL", "Field start")
        except ValueError:
            pass
    return BUNDLED_HOME, BUNDLED_HOME_LABEL


def resolve_field_job() -> FieldJobFixture:
    """Director override: TD_JOB_XLS + TD_JOB_EST (semicolon-separated, optional path|label)."""
    manifest = os.environ.get("TD_JOB_MANIFEST", "").strip()
    if manifest and os.path.isfile(manifest):
        with open(manifest, encoding="utf-8") as f:
            data = json.load(f)
        ests = tuple(
            (e["path"], e.get("label", f"Day {i + 1}"))
            for i, e in enumerate(data.get("ests", []))
        )
        home = tuple(data.get("home", BUNDLED_HOME))
        return FieldJobFixture(
            label=data.get("label", "manifest job"),
            xls=data["xls"],
            ests=ests,
            home=(float(home[0]), float(home[1])),
            home_label=data.get("home_label", "Field start"),
            source="manifest",
        )

    xls = os.environ.get("TD_JOB_XLS", "").strip()
    est_raw = os.environ.get("TD_JOB_EST", "").strip()
    if xls and est_raw:
        home, home_label = _home_from_env()
        return FieldJobFixture(
            label=os.environ.get("TD_JOB_LABEL", "director job"),
            xls=xls,
            ests=_parse_est_list(est_raw),
            home=home,
            home_label=home_label,
            source="env",
        )

    return FieldJobFixture(
        label="bundled validation job",
        xls=BUNDLED_XLS,
        ests=BUNDLED_ESTS,
        home=BUNDLED_HOME,
        home_label=BUNDLED_HOME_LABEL,
        source="bundled",
    )


def director_job_override_active() -> bool:
    return resolve_field_job().source != "bundled"
