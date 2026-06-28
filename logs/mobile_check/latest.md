# Mobile app check

- When: 2026-06-28T07:50:04.971928+00:00
- Result: PASS
- Duration: 27.7s

## Steps

- [OK] `user_prove` — 11.5s
- [OK] `tls_prove` — 2.4s
- [OK] `share_prove` — 1.9s
- [OK] `stress_loop` — 11.9s

## Strengths

- User flow: 26/26 checks pass (import, route, phone GPS grab, pin fallback, install, pickup, export, error paths)
- Job token enforced; out-of-bounds GPS and bad uploads rejected with clear errors
- HTTPS secure context: 11/11 TLS checks pass (self-signed cert names the LAN IP; real handshake serves /api/healthz; phone geolocation works over LAN)
- Public share mode: 32/32 checks pass (share links open jobs anywhere; public start page can't create/browse; creation is admin-key gated; QR generated; wrong token/key rejected; links can be revoked and self-expire)
- Full install cycle clean over 5 stops
- Map-state latency p50=3.1ms p95=4.7ms (budget 250.0ms)
- Concurrent grab+patch on one stop: no lost writes, job intact

## Weaknesses

- (none blocking) — see improvements for next-step polish

## Improvements / next steps

- HTTPS over LAN now on by default (self-signed); phone must accept the cert once — use a trusted cert / reverse proxy to skip the warning in production
- Always-on host deploy ready (Dockerfile + render.yaml/fly.toml, proven via scripts/mobile_host_smoke.py); laptop Cloudflare tunnel remains the default — deploy to Render/Fly for a 24/7 URL without the laptop on
- Share links now support revoke + self-expiry (TD_MOBILE_LINK_TTL_HOURS, scripts/manage_share_link.py); full multi-user auth still phase 2
- Hosted deploy means job data lives on the host — use same-Wi-Fi mode for data that must never leave the machine
- Offline field mode not implemented — online-first; brief drops not yet queued in IndexedDB
- Server-side road graph optional — without it, routes are straight-line, not street-traced
- No undo on mobile install/skip (desktop has undo)
- Browser/device E2E (Playwright) not wired — current proof is in-process API simulation
- 80-stop job: map-state 36.7KB, edit p95 6.2ms — add list virtualization/search if payload grows; background heavy route builds
