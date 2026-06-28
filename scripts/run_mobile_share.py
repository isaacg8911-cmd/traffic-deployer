"""Public SHARE mode: serve the mobile PWA over a Cloudflare quick tunnel.

This is the "text a link, phone works anywhere" path. It:

  1. turns on share-only public mode (crew can only open jobs via a share link;
     job creation requires the admin key),
  2. starts the mobile server on localhost (plain HTTP — Cloudflare terminates
     TLS at its edge and gives a public https:// URL),
  3. launches `cloudflared tunnel --url http://127.0.0.1:PORT`,
  4. discovers the public https://<name>.trycloudflare.com URL and feeds it back
     so share links are absolute and correct,
  5. optionally creates a demo job and prints its ready-to-send share link.

Requirements:
  - cloudflared on PATH (or set TD_CLOUDFLARED to its full path).
    Install: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
    (Windows: `winget install --id Cloudflare.cloudflared`)

Nothing is exposed without the tunnel; stop it with Ctrl+C and the URL dies.

Usage:
  .venv\\Scripts\\python.exe scripts\\run_mobile_share.py            # serve + tunnel
  .venv\\Scripts\\python.exe scripts\\run_mobile_share.py --demo     # also make a demo job link
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TUNNEL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def _find_cloudflared() -> str | None:
    env = os.environ.get("TD_CLOUDFLARED", "").strip()
    if env and os.path.isfile(env):
        return env
    return shutil.which("cloudflared")


def _start_server(port: int) -> threading.Thread:
    import uvicorn

    # Public mode is read from the environment by mobile_web.settings at runtime.
    config = uvicorn.Config(
        "mobile_web.server:app", host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if getattr(server, "started", False):
            break
        time.sleep(0.1)
    thread._server = server  # type: ignore[attr-defined]
    return thread


def _start_tunnel(cloudflared: str, port: int) -> tuple[subprocess.Popen, str]:
    proc = subprocess.Popen(
        [cloudflared, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    public_url = ""
    deadline = time.time() + 40
    while time.time() < deadline:
        line = proc.stdout.readline() if proc.stdout else ""
        if not line:
            if proc.poll() is not None:
                break
            continue
        m = TUNNEL_RE.search(line)
        if m:
            public_url = m.group(0)
            break
    # Keep draining the pipe so cloudflared does not block on a full buffer.
    threading.Thread(target=_drain, args=(proc,), daemon=True).start()
    return proc, public_url


def _drain(proc: subprocess.Popen) -> None:
    if not proc.stdout:
        return
    for _ in proc.stdout:
        pass


def _make_demo(port: int, admin_key: str) -> str:
    import httpx

    headers = {"x-admin-key": admin_key} if admin_key else {}
    r = httpx.post(f"http://127.0.0.1:{port}/api/jobs/demo", headers=headers, timeout=180.0)
    r.raise_for_status()
    return r.json().get("share_url", "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mobile public share mode (Cloudflare tunnel).")
    parser.add_argument("--demo", action="store_true", help="create a demo job and print its share link")
    parser.add_argument(
        "--open-uploads",
        action="store_true",
        help="let the phone upload its own Excel + .EST on the public URL (no admin key)",
    )
    parser.add_argument("--port", type=int, default=int(os.environ.get("TD_MOBILE_PORT", "8800")))
    args = parser.parse_args()

    os.environ["TD_MOBILE_PUBLIC"] = "1"
    if args.open_uploads:
        os.environ["TD_MOBILE_OPEN_CREATE"] = "1"

    from mobile_web import settings

    cloudflared = _find_cloudflared()
    if not cloudflared:
        print("=" * 64)
        print(" cloudflared not found — cannot open a public tunnel.")
        print(" Install it, then re-run:")
        print("   winget install --id Cloudflare.cloudflared")
        print("   (or set TD_CLOUDFLARED to the cloudflared.exe path)")
        print(" For same-Wi-Fi use instead, run RUN_MOBILE.bat.")
        print("=" * 64)
        return 2

    admin_key = settings.admin_key()

    print("=" * 64)
    print(" Traffic Deployer — MOBILE public SHARE mode")
    print("=" * 64)
    print(" Starting server + Cloudflare tunnel… (first time can take ~10s)")

    server_thread = _start_server(args.port)
    proc, public_url = _start_tunnel(cloudflared, args.port)

    if not public_url:
        print(" [error] Could not get a tunnel URL from cloudflared.")
        try:
            proc.terminate()
        except Exception:
            pass
        return 1

    os.environ["TD_MOBILE_PUBLIC_URL"] = public_url

    print("=" * 64)
    print(f"  PUBLIC URL : {public_url}")
    if settings.open_uploads():
        print("  Mode       : OPEN uploads (open this URL on the phone and import")
        print("               your Excel + .EST directly — no demo, no admin key)")
    else:
        print("  Mode       : share-only (crew open jobs from a share link)")
    if settings.admin_key_is_generated():
        print(f"  ADMIN KEY  : {admin_key}")
        print("               (needed to create jobs on the public server;")
        print("                send 'x-admin-key' header. Set TD_MOBILE_ADMIN_KEY to pin it.)")
    else:
        print("  ADMIN KEY  : (from TD_MOBILE_ADMIN_KEY)")
    print("=" * 64)

    if args.demo:
        try:
            share = _make_demo(args.port, admin_key)
            print("  DEMO JOB share link (text this to a phone):")
            print(f"    {share}")
            print("=" * 64)
        except Exception as exc:  # pragma: no cover - network/runtime
            print(f"  [warn] could not create demo job: {exc}")

    print("  Stop: Ctrl+C (this kills the public URL).")
    try:
        while True:
            time.sleep(1)
            if proc.poll() is not None:
                print(" [warn] cloudflared exited; public URL is down.")
                break
    except KeyboardInterrupt:
        print("\n Shutting down tunnel…")
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        srv = getattr(server_thread, "_server", None)
        if srv is not None:
            srv.should_exit = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
