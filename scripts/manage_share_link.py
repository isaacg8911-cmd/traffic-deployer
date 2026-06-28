"""Manage mobile share links from the laptop — revoke / extend / status.

Runs against a live mobile server (local Wi-Fi, Cloudflare tunnel, or a hosted
deploy). Share-link management is admin-only, so this needs the admin key.

The job argument can be a bare job id OR a full share link
(https://host/join/<id>?token=...). The token is ignored here; management uses
the admin key, not the per-job token.

Examples:
  # Revoke a lost phone's link (against the hosted server)
  python scripts/manage_share_link.py revoke https://td.onrender.com/join/ab12...?token=xyz \
      --url https://td.onrender.com --admin-key $TD_MOBILE_ADMIN_KEY

  # Give a link 8 more hours
  python scripts/manage_share_link.py extend ab12cd34ef56 --hours 8 --url http://127.0.0.1:8800

  # Make a link never expire (also un-revokes it)
  python scripts/manage_share_link.py extend ab12cd34ef56 --hours 0

  # Check a link's state
  python scripts/manage_share_link.py status ab12cd34ef56

Defaults: --url from TD_MOBILE_PUBLIC_URL or http://127.0.0.1:8800,
          --admin-key from TD_MOBILE_ADMIN_KEY.
Exit 0 on success.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

_JOIN_RE = re.compile(r"/join/([A-Za-z0-9_-]+)")


def _job_id(arg: str) -> str:
    m = _JOIN_RE.search(arg)
    return m.group(1) if m else arg.strip()


def _default_url() -> str:
    return (os.environ.get("TD_MOBILE_PUBLIC_URL", "").strip().rstrip("/")
            or "http://127.0.0.1:8800")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Manage mobile share links (admin).")
    p.add_argument("action", choices=["status", "revoke", "extend"])
    p.add_argument("job", help="job id or a full /join/<id> share link")
    p.add_argument("--hours", type=float, default=None,
                   help="extend: new TTL in hours (<=0 = never expire, also un-revokes)")
    p.add_argument("--url", default=_default_url(), help="server base URL")
    p.add_argument("--admin-key", default=os.environ.get("TD_MOBILE_ADMIN_KEY", "").strip())
    args = p.parse_args(argv)

    try:
        import httpx
    except ImportError:
        print("httpx is required: pip install -r mobile_web/requirements.txt", file=sys.stderr)
        return 2

    job_id = _job_id(args.job)
    base = args.url.rstrip("/")
    headers = {"x-admin-key": args.admin_key} if args.admin_key else {}

    try:
        if args.action == "status":
            r = httpx.get(f"{base}/api/jobs/{job_id}/status", headers=headers, timeout=30.0)
        elif args.action == "revoke":
            r = httpx.post(f"{base}/api/jobs/{job_id}/revoke", headers=headers, timeout=30.0)
        else:  # extend
            payload = {} if args.hours is None else {"hours": args.hours}
            r = httpx.post(f"{base}/api/jobs/{job_id}/extend", headers=headers,
                           json=payload, timeout=30.0)
    except httpx.HTTPError as exc:
        print(f"[error] could not reach {base}: {exc}", file=sys.stderr)
        return 1

    if r.status_code == 403:
        print("[error] admin key rejected — set --admin-key or TD_MOBILE_ADMIN_KEY.",
              file=sys.stderr)
        return 1
    if r.status_code == 404:
        print(f"[error] job {job_id} not found on {base}.", file=sys.stderr)
        return 1
    if r.status_code != 200:
        print(f"[error] HTTP {r.status_code}: {r.text}", file=sys.stderr)
        return 1

    data = r.json()
    status = data.get("link_status", "?")
    exp = data.get("expires_at")
    when = ""
    if exp:
        import datetime as _dt
        when = " (expires " + _dt.datetime.fromtimestamp(float(exp)).strftime("%Y-%m-%d %H:%M") + ")"
    print(f"{args.action}: job {job_id} -> {status}{when}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
