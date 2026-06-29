# Mobile app check

- When: 2026-06-29T05:44:43.002813+00:00
- Result: PASS
- Duration: 19.5s

## Steps

- [OK] `user_prove` — 7.4s
- [OK] `share_prove` — 1.8s
- [OK] `stress_loop` — 8.0s
- [SKIP] `browser_prove` — 2.4s

## Strengths

- User flow: 29/29 checks pass (import, route, phone GPS grab, pin fallback, install, pickup, export, error paths)
- Job token enforced; out-of-bounds GPS and bad uploads rejected with clear errors
- Public share mode: 32/32 checks pass (share links open jobs anywhere; public start page can't create/browse; creation is admin-key gated; QR generated; wrong token/key rejected; links can be revoked and self-expire)
- Full install cycle clean over 5 stops
- Map-state latency p50=3.3ms p95=4.8ms (budget 250.0ms)
- Concurrent grab+patch on one stop: no lost writes, job intact

## Weaknesses

- (none blocking) — see improvements for next-step polish

## Improvements / next steps

- Render is the only hosted surface — Dockerfile + render.yaml; prove with scripts/mobile_host_smoke.py (share-only) and mobile_live_host_prove.py
- Share links support revoke + self-expiry (TD_MOBILE_LINK_TTL_HOURS, scripts/manage_share_link.py); full multi-user auth still phase 2
- Hosted deploy means job data lives on Render — not for data that must never leave your machine
- Offline queue (IndexedDB) not implemented — banner blocks saves when offline
- Server-side road graph optional — without it, routes are straight-line, not street-traced
- No undo on mobile install/skip (desktop has undo)
- 80-stop job: map-state 36.7KB, edit p95 7.2ms — add list virtualization/search if payload grows; background heavy route builds
- Browser proof skipped (install playwright + chromium) — scripts/mobile_browser_prove.py
