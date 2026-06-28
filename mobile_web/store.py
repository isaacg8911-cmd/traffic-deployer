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


def _expiry_from_hours(hours: float | None) -> float | None:
    """Absolute unix-time expiry from a TTL in hours, or None for no expiry."""
    if hours is None:
        return None
    try:
        h = float(hours)
    except (TypeError, ValueError):
        return None
    return _now() + h * 3600.0 if h > 0 else None


def link_status(job: dict) -> str:
    """Share-link state: 'active' | 'revoked' | 'expired'.

    Tolerant of legacy jobs written before these fields existed (treated active).
    """
    if job.get("revoked"):
        return "revoked"
    exp = job.get("expires_at")
    if exp is not None:
        try:
            if _now() >= float(exp):
                return "expired"
        except (TypeError, ValueError):
            pass
    return "active"


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
        expires_in_hours: float | None = None,
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
            # Share-link controls (phase 2): a lost phone can be cut off by
            # revoking, and links can self-expire after the shift.
            "revoked": False,
            "expires_at": _expiry_from_hours(expires_in_hours),
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
        # A revoked or expired link must not open the job, even with a valid token.
        if link_status(job) != "active":
            return None
        return job

    def save(self, job: dict) -> None:
        self._write(job)

    def revoke(self, job_id: str) -> dict | None:
        """Cut off a share link (e.g. a lost phone). Returns the job or None."""
        with _LOCK:
            job = self.load(job_id)
            if job is None:
                return None
            job["revoked"] = True
            self._write(job)
            return job

    def set_expiry(self, job_id: str, expires_in_hours: float | None) -> dict | None:
        """Re-activate a link and (re)set its expiry.

        hours None or <= 0 clears expiry (link never times out). Always clears the
        revoked flag, so this doubles as "un-revoke / extend". Returns job or None.
        """
        with _LOCK:
            job = self.load(job_id)
            if job is None:
                return None
            job["expires_at"] = _expiry_from_hours(expires_in_hours)
            job["revoked"] = False
            self._write(job)
            return job

    def update_stop(self, job: dict, uid: str, patch: dict) -> dict | None:
        """Apply a whitelisted field patch to one stop; returns the stop or None."""
        with _LOCK:
            for stop in job["stops"]:
                if stop.get("uid") == uid:
                    _apply_stop_patch(stop, patch)
                    self._write(job)
                    return stop
        return None

    def move_stop(self, job: dict, uid: str, direction: str) -> str:
        """Move one stop up/down in the manual order.

        Returns: 'moved' | 'edge' (already at top/bottom) | 'not_found'.
        Does NOT persist — the caller saves after re-tracing so the write is
        atomic with the new route. Pure list reorder; numbering is derived from
        position in `map_state.build_map_state`, so nothing else to renumber.
        """
        if direction not in ("up", "down"):
            raise ValueError("direction must be 'up' or 'down'")
        with _LOCK:
            stops = job.get("stops") or []
            idx = next((i for i, s in enumerate(stops) if s.get("uid") == uid), -1)
            if idx < 0:
                return "not_found"
            swap = idx - 1 if direction == "up" else idx + 1
            if swap < 0 or swap >= len(stops):
                return "edge"
            stops[idx], stops[swap] = stops[swap], stops[idx]
            return "moved"

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
        "link_status": link_status(job),
        "expires_at": job.get("expires_at"),
    }
