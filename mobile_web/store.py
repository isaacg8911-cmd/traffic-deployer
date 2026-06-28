"""Web-safe job store for the mobile lane.

Plain JSON files under tds_data/mobile_jobs/. Intentionally does NOT use the
desktop `persistence` module (encrypted local-first single-shift store) because
the mobile lane is multi-job and server-side. Each job carries a random token;
clients must present it, so jobs are not enumerable by id alone.

This is MVP-grade scoping, not full multi-tenant auth (phase 2).
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
import uuid

_LOCK = threading.RLock()


def _now() -> float:
    return time.time()


class JobStore:
    def __init__(self, root: str):
        self.root = root
        os.makedirs(self.root, exist_ok=True)
        # In-process cache: the server is the only writer, so a loaded job dict
        # is authoritative until the next write. Cuts disk read + JSON parse off
        # the hot map-state path.
        self._cache: dict[str, dict] = {}

    def _path(self, job_id: str) -> str:
        safe = "".join(c for c in job_id if c.isalnum() or c in "-_")
        return os.path.join(self.root, f"{safe}.json")

    def create(
        self,
        *,
        home: tuple[float, float],
        home_label: str,
        stops: list[dict],
        active_files: list[str],
        label: str = "",
    ) -> dict:
        job_id = uuid.uuid4().hex[:12]
        token = secrets.token_urlsafe(18)
        job = {
            "id": job_id,
            "token": token,
            "label": label or "Mobile job",
            "created": _now(),
            "updated": _now(),
            "home": [float(home[0]), float(home[1])],
            "home_label": home_label,
            "active_files": list(active_files),
            "stops": stops,
            "route": {"polyline": [], "miles": 0.0, "graph": False},
        }
        self._write(job)
        return job

    def _write(self, job: dict) -> None:
        job["updated"] = _now()
        with _LOCK:
            tmp = self._path(job["id"]) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(job, f, ensure_ascii=False)
            os.replace(tmp, self._path(job["id"]))
            self._cache[job["id"]] = job

    def load(self, job_id: str) -> dict | None:
        with _LOCK:
            cached = self._cache.get(job_id)
            if cached is not None:
                return cached
            path = self._path(job_id)
            if not os.path.isfile(path):
                return None
            try:
                with open(path, encoding="utf-8") as f:
                    job = json.load(f)
            except (OSError, json.JSONDecodeError):
                return None
            self._cache[job_id] = job
            return job

    def get_authorized(self, job_id: str, token: str) -> dict | None:
        job = self.load(job_id)
        if job is None:
            return None
        if not token or not secrets.compare_digest(str(job.get("token", "")), str(token)):
            return None
        return job

    def save(self, job: dict) -> None:
        self._write(job)

    def update_stop(self, job: dict, uid: str, patch: dict) -> dict | None:
        """Apply a whitelisted field patch to one stop; returns the stop or None."""
        with _LOCK:
            for stop in job["stops"]:
                if stop.get("uid") == uid:
                    _apply_stop_patch(stop, patch)
                    self._write(job)
                    return stop
        return None

    def delete(self, job_id: str) -> bool:
        path = self._path(job_id)
        with _LOCK:
            self._cache.pop(job_id, None)
            if os.path.isfile(path):
                os.remove(path)
                return True
        return False

    def purge_older_than(self, max_age_s: float) -> int:
        """Delete jobs untouched for longer than max_age_s. Returns count removed."""
        cutoff = _now() - max_age_s
        removed = 0
        with _LOCK:
            for name in os.listdir(self.root):
                if not name.endswith(".json"):
                    continue
                path = os.path.join(self.root, name)
                try:
                    if os.path.getmtime(path) < cutoff:
                        os.remove(path)
                        job_id = name[:-len(".json")]
                        self._cache.pop(job_id, None)
                        removed += 1
                except OSError:
                    pass
        return removed


_EDITABLE_TEXT = ("street", "direction", "notes", "serial")
_EDITABLE_FLAGS = ("installed", "skipped", "picked_up")


def _apply_stop_patch(stop: dict, patch: dict) -> None:
    from core.state import ca_now

    for key in _EDITABLE_TEXT:
        if key in patch and patch[key] is not None:
            stop[key] = str(patch[key])[:300]
    if "lanes" in patch and patch["lanes"] is not None:
        try:
            stop["lanes"] = max(1, min(20, int(patch["lanes"])))
        except (TypeError, ValueError):
            pass
    for key in _EDITABLE_FLAGS:
        if key in patch and patch[key] is not None:
            stop[key] = bool(patch[key])
    # Stamp install/pickup time the same way the desktop does.
    if patch.get("installed") and not stop.get("date"):
        date, exact = ca_now()
        stop["date"], stop["exact_time"] = date, exact


def public_job(job: dict) -> dict:
    """Job view without the secret token."""
    return {
        "id": job["id"],
        "label": job.get("label", ""),
        "home": job.get("home"),
        "home_label": job.get("home_label", ""),
        "active_files": job.get("active_files", []),
        "created": job.get("created"),
        "updated": job.get("updated"),
        "stop_count": len(job.get("stops", [])),
    }
