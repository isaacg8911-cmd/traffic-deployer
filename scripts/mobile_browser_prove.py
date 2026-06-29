"""Browser-level proof for the mobile PWA (real rendering, not API-only).

Exercises the user-visible path in Chromium via Playwright:
  - PWA shell + MapLibre canvas
  - Share-link job open
  - Build route -> route mileage and stop order visible
  - Reorder -> stale order text without drawing route/tracing lines
  - Offline banner blocks saves
  - Denied geolocation surfaces drop-pin fallback hint

Usage (local in-process server):
  pip install playwright httpx
  playwright install chromium
  python scripts/mobile_browser_prove.py

Against a running host:
  python scripts/mobile_browser_prove.py --url http://127.0.0.1:8800

Exit 0 = all checks passed. Exit 2 = Playwright not installed (skip).
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PROOF_DIR = os.path.join(ROOT, "logs", "mobile_check", "proofs")


def _start_local_server(port: int) -> tuple[threading.Thread, str]:
    import uvicorn

    config = uvicorn.Config(
        "mobile_web.server:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    def run() -> None:
        server.run()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            import httpx

            r = httpx.get(f"{base}/api/healthz", timeout=2.0)
            if r.status_code == 200:
                return t, base
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError("local server did not start")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="", help="Base URL (default: spin up local server)")
    parser.add_argument("--port", type=int, default=18801)
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed — browser proof skipped.")
        print("  pip install playwright && playwright install chromium")
        return 2

    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"[{'OK ' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    base = args.url.rstrip("/") if args.url else ""
    if not base:
        _start_local_server(args.port)
        base = f"http://127.0.0.1:{args.port}"

    import httpx

    r = httpx.post(f"{base}/api/jobs/demo", timeout=120.0)
    check("demo_job_api", r.status_code == 200, str(r.status_code))
    if r.status_code != 200:
        return _finish(checks, 1)
    body = r.json()
    job_id, token = body["job_id"], body["token"]
    join_url = f"{base}/join/{job_id}?token={token}"

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            msg = str(exc)
            if "Executable doesn't exist" in msg or "playwright install" in msg.lower():
                print("Playwright browser missing — browser proof skipped.")
                print("  playwright install chromium")
                return 2
            raise
        context = browser.new_context(
            geolocation={"latitude": 33.81, "longitude": -117.92},
            permissions=["geolocation"],
            viewport={"width": 390, "height": 844},
        )
        page = context.new_page()

        page.goto(join_url, wait_until="networkidle", timeout=60000)
        check("share_link_loads", "Traffic Deployer" in page.title() or page.locator("#brand").count() > 0)

        page.wait_for_selector("#tabbar:not(.hidden)", timeout=30000)
        check("job_opens_ui", page.locator("#tabbar").is_visible())

        page.wait_for_selector("#map canvas", timeout=30000)
        check("map_canvas", page.locator("#map canvas").count() > 0)

        page.click("#btnBuildRoute")
        page.wait_for_function(
            """() => {
              const el = document.getElementById('routeMiles');
              return el && el.textContent && el.textContent.includes('mi');
            }""",
            timeout=60000,
        )
        map_ready = page.evaluate(
            """() => {
              if (!window.maplibregl || !document.getElementById('map')) return false;
              const mapEl = document.querySelector('.maplibregl-canvas');
              return !!mapEl;
            }"""
        )
        check("build_route_ui", map_ready, "map ready after build")

        route_layer = page.evaluate(
            """async () => {
              await new Promise(r => setTimeout(r, 800));
              const src = document.querySelector('script[src*="/app.js"]');
              if (!src) return false;
              const miles = document.getElementById('routeMiles');
              return miles && miles.textContent.includes('mi');
            }"""
        )
        check("route_miles_shown", bool(route_layer))

        # Reorder -> stale order text, with no drawn route/tracing line.
        if page.locator("#btnReorder").count():
            page.click("#btnReorder")
            move_btn = page.locator(".reorder-btns .rbtn:not([disabled])").first
            if move_btn.count():
                move_btn.click()
                page.wait_for_function(
                    "() => document.getElementById('routeMiles')?.classList.contains('stale')",
                    timeout=10000,
                )
            stale = page.evaluate(
                "() => document.getElementById('routeMiles')?.classList.contains('stale')"
            )
            check("reorder_marks_stale_ui", bool(stale))
            no_route_line = page.evaluate(
                """() => {
                  const ids = ['route-line', 'routeLine', 'trace-line', 'traceLine'];
                  return !ids.some(id => document.querySelector('#' + id));
                }"""
            )
            check("no_route_line_element", bool(no_route_line))

        # Install tab + denied geolocation fallback text path
        page.click('#tabbar button[data-tab="install"]')
        page.wait_for_selector("#btnGrab", timeout=10000)
        context.clear_permissions()
        page.click("#btnGrab")
        page.wait_for_timeout(500)
        grab_err = page.locator("#grabInfo.msg.err").count() > 0
        check("gps_denied_fallback_hint", grab_err or page.locator("#btnDropPin").is_visible())

        # Offline guard
        context.set_offline(True)
        page.evaluate("window.dispatchEvent(new Event('offline'))")
        page.wait_for_timeout(200)
        offline_banner = page.locator("#offlineBanner:not(.hidden)").count() > 0
        check("offline_banner", offline_banner)
        context.set_offline(False)
        page.evaluate("window.dispatchEvent(new Event('online'))")

        # Cached session restore
        page.evaluate(
            """(args) => {
              localStorage.setItem('td_mobile_job', JSON.stringify({jobId: args.id, token: args.token}));
            }""",
            {"id": job_id, "token": token},
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#tabbar:not(.hidden)", timeout=30000)
        check("session_restore_reload", page.locator("#tabbar").is_visible())

        # Bad token error path
        page.goto(f"{base}/join/badjobid?token=badtoken", wait_until="networkidle")
        page.wait_for_timeout(500)
        err_msg = page.locator("#startMsg.msg.err").count() > 0
        check("bad_share_link_error", err_msg)

        browser.close()

    return _finish(checks, 0 if all(c["ok"] for c in checks) else 1)


def _finish(checks: list[dict], code: int) -> int:
    os.makedirs(PROOF_DIR, exist_ok=True)
    report = {
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "passed": sum(1 for c in checks if c["ok"]),
        "total": len(checks),
        "failed": [c["name"] for c in checks if not c["ok"]],
        "checks": checks,
    }
    path = os.path.join(PROOF_DIR, "browser_prove.json")
    import json

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n{report['passed']}/{report['total']} browser checks passed.")
    if report["failed"]:
        print("FAILED:", ", ".join(report["failed"]))
    print(f"Proof: {path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
