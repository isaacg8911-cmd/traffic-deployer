"""Optional online update check (home Wi‑Fi only).

Configure release URL via tds_data/update_channel.json or env TD_UPDATE_URL.
Expected remote version.json:
  {"version": "1.0.7", "download_url": "https://...zip", "sha256": "...",
   "notes": "...", "published": "2026-06-07"}
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from ui.paths import DATA_DIR

CHANNEL_FILE = os.path.join(DATA_DIR, "update_channel.json")
DEFAULT_TIMEOUT_S = 12


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class UpdateInfo:
    current: str
    latest: str
    update_available: bool
    download_url: str
    notes: str
    sha256: str = ""
    error: str = ""


def _parse_version(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in (v or "0").strip().split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def version_gt(a: str, b: str) -> bool:
    return _parse_version(a) > _parse_version(b)


def channel_url() -> str | None:
    url = os.environ.get("TD_UPDATE_URL", "").strip()
    if url:
        return url
    if os.path.isfile(CHANNEL_FILE):
        try:
            with open(CHANNEL_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return str(data.get("version_url") or data.get("url") or "").strip() or None
        except (OSError, json.JSONDecodeError):
            return None
    return None


def fetch_remote_version(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "TrafficDeployer-UpdateCheck"})
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_for_update(current_version: str) -> UpdateInfo:
    url = channel_url()
    if not url:
        return UpdateInfo(
            current=current_version,
            latest=current_version,
            update_available=False,
            download_url="",
            notes="",
            error="No update channel configured (tds_data/update_channel.json or TD_UPDATE_URL).",
        )
    try:
        data = fetch_remote_version(url)
        latest = str(data.get("version", "")).strip() or current_version
        return UpdateInfo(
            current=current_version,
            latest=latest,
            update_available=version_gt(latest, current_version),
            download_url=str(data.get("download_url") or "").strip(),
            notes=str(data.get("notes") or "").strip(),
            sha256=str(data.get("sha256") or "").strip(),
        )
    except urllib.error.URLError as exc:
        return UpdateInfo(
            current=current_version,
            latest=current_version,
            update_available=False,
            download_url="",
            notes="",
            error=f"Could not reach update server: {exc}",
        )
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        return UpdateInfo(
            current=current_version,
            latest=current_version,
            update_available=False,
            download_url="",
            notes="",
            error=f"Invalid update manifest: {exc}",
        )
