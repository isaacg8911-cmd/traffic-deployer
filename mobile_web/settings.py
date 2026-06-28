"""Runtime settings for the mobile lane — share-only public mode + admin key.

Two deployment shapes:

  LOCAL (default)   TD_MOBILE_PUBLIC unset
    - Same Wi-Fi / hotspot. The start screen can create demo/import jobs.
    - Admin key optional.

  PUBLIC (share-only)   TD_MOBILE_PUBLIC=1
    - Reachable over the internet (tunnel / host). The crew may ONLY open a job
      via a share link (/join/<job_id>?token=<secret>). The public start screen
      hides job creation; there is no public job list.
    - Job creation (demo/import) requires the admin key (TD_MOBILE_ADMIN_KEY)
      via the `x-admin-key` header, so random visitors cannot create jobs.

The admin key is read from the environment only; never committed. If public mode
is on and no admin key is set, one is generated at startup and printed by the
launcher (so the Director still has a way in).
"""
from __future__ import annotations

import os
import secrets

_GENERATED_ADMIN_KEY: str | None = None


def public_mode() -> bool:
    return os.environ.get("TD_MOBILE_PUBLIC", "") == "1"


def admin_key() -> str:
    """The admin key for privileged actions (job creation in public mode).

    Order: explicit env key -> a process-lifetime generated key (public mode) ->
    empty string (local mode with no key set, i.e. creation is open).
    """
    global _GENERATED_ADMIN_KEY
    env = os.environ.get("TD_MOBILE_ADMIN_KEY", "").strip()
    if env:
        return env
    if public_mode():
        if _GENERATED_ADMIN_KEY is None:
            _GENERATED_ADMIN_KEY = secrets.token_urlsafe(18)
        return _GENERATED_ADMIN_KEY
    return ""


def admin_key_is_generated() -> bool:
    """True if the active admin key was auto-generated (not supplied via env)."""
    return not os.environ.get("TD_MOBILE_ADMIN_KEY", "").strip() and public_mode()


def public_base_url() -> str:
    """Public origin for building share links, e.g. https://x.trycloudflare.com.

    Empty when unknown (local mode); the client then falls back to its own origin.
    """
    return os.environ.get("TD_MOBILE_PUBLIC_URL", "").strip().rstrip("/")


def default_link_ttl_hours() -> float:
    """Default share-link lifetime in hours (TD_MOBILE_LINK_TTL_HOURS).

    0 / unset = links never expire unless a per-job expiry is given. A host
    deploy typically sets this (e.g. 16) so a shift's links self-expire.
    """
    raw = os.environ.get("TD_MOBILE_LINK_TTL_HOURS", "").strip()
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return v if v > 0 else 0.0


def creation_allowed(admin_header: str | None) -> bool:
    """Whether a job-creation request is allowed given the presented admin key."""
    key = admin_key()
    if not public_mode() and not key:
        # Local mode, no key configured: open creation (same as before).
        return True
    if not key:
        return False
    return bool(admin_header) and secrets.compare_digest(str(admin_header), key)
