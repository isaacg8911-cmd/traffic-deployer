"""Optional online update check (home Wi‑Fi or Tailscale).

Configure via tds_data/update_channel.json, wifi_update_home.txt, or env
TD_UPDATE_URL / TD_UPDATE_HOME. Manifest version.json:

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
from urllib.parse import urlparse, urlunparse

from ui.paths import APP_DIR, DATA_DIR

CHANNEL_FILE = os.path.join(DATA_DIR, "update_channel.json")
HOME_TXT = os.path.join(APP_DIR, "wifi_update_home.txt")
DEFAULT_TIMEOUT_S = 12
DEFAULT_ZIP = "TrafficDeployer-AppUpdate.zip"


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
    manifest_url: str = ""


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


def _add_url(urls: list[str], raw: str) -> None:
    text = (raw or "").strip()
    if not text:
        return
    if text.startswith("http://") or text.startswith("https://"):
        if not text.lower().endswith(".json"):
            text = text.rstrip("/") + "/version.json"
        if text not in urls:
            urls.append(text)


def channel_urls() -> list[str]:
    """All candidate manifest URLs (Tailscale first when the channel lists them)."""
    urls: list[str] = []
    _add_url(urls, os.environ.get("TD_UPDATE_URL", ""))
    home = os.environ.get("TD_UPDATE_HOME", "").strip()
    if home:
        _add_url(urls, home)
    if os.path.isfile(CHANNEL_FILE):
        try:
            with open(CHANNEL_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = None
        if isinstance(data, dict):
            extra = data.get("version_urls") or data.get("homes") or []
            if isinstance(extra, str):
                extra = [extra]
            for item in extra:
                _add_url(urls, str(item))
            _add_url(urls, str(data.get("version_url") or data.get("url") or ""))
    if os.path.isfile(HOME_TXT):
        try:
            with open(HOME_TXT, encoding="utf-8") as f:
                for line in f:
                    _add_url(urls, line)
        except OSError:
            pass
    return urls


def channel_url() -> str | None:
    urls = channel_urls()
    return urls[0] if urls else None


def rewrite_download_url(
    manifest_url: str,
    download_url: str,
    zip_name: str = DEFAULT_ZIP,
) -> str:
    """Keep the zip path, but download from the host that actually answered.

    Manifest may list a LAN IP the laptop cannot reach when it is on Tailscale.
    """
    parsed = urlparse(manifest_url)
    if not parsed.netloc:
        return (download_url or "").strip()
    path = "/" + zip_name.lstrip("/")
    if download_url:
        down = urlparse(download_url)
        if down.path:
            path = down.path
    return urlunparse((parsed.scheme or "http", parsed.netloc, path, "", "", ""))


def fetch_remote_version(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "TrafficDeployer-UpdateCheck"})
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8-sig"))


def check_for_update(current_version: str) -> UpdateInfo:
    urls = channel_urls()
    if not urls:
        return UpdateInfo(
            current=current_version,
            latest=current_version,
            update_available=False,
            download_url="",
            notes="",
            error="No update channel configured (tds_data/update_channel.json or TD_UPDATE_URL).",
        )
    errors: list[str] = []
    for url in urls:
        try:
            data = fetch_remote_version(url)
            latest = str(data.get("version", "")).strip() or current_version
            download = rewrite_download_url(url, str(data.get("download_url") or "").strip())
            return UpdateInfo(
                current=current_version,
                latest=latest,
                update_available=version_gt(latest, current_version),
                download_url=download,
                notes=str(data.get("notes") or "").strip(),
                sha256=str(data.get("sha256") or "").strip(),
                manifest_url=url,
            )
        except urllib.error.URLError as exc:
            errors.append(f"{url} ({exc})")
        except (json.JSONDecodeError, OSError, KeyError, ValueError) as exc:
            errors.append(f"{url} (invalid manifest: {exc})")
    detail = "; ".join(errors[:4])
    return UpdateInfo(
        current=current_version,
        latest=current_version,
        update_available=False,
        download_url="",
        notes="",
        error=f"Could not reach update server: {detail}",
    )
