# Mobile Web (phone field runner)

A lean, online-first PWA companion to the desktop app. It reuses the desktop
core (ingest, routing, export) but drops USB GPS, the PicoCount workflow, and the
Qt shell. Location comes from the phone browser.

## Run it

```
RUN_MOBILE.bat
```

This starts the server (HTTPS by default) and prints two URLs:

- On this PC: `https://127.0.0.1:8800`
- On phone: `https://<lan-ip>:8800` (same Wi-Fi)

Open the phone URL, then "Add to Home Screen" to install the app icon.

First request is slow (~2 min) the first time because the routing engine imports
osmnx on startup; after that it is fast.

### Geolocation note

Phone browser geolocation needs a **secure context** — over LAN by IP the
browser blocks `getCurrentPosition` on plain HTTP. The launcher now serves
**HTTPS by default** using a self-signed certificate that names this PC's LAN IP
(generated into `tds_data/mobile_certs/`, git-ignored). The phone shows a
one-time "connection is not private" warning — tap **Advanced -> proceed** — and
then "Grab GPS" works in the field.

For a warning-free experience in production, put the server behind a trusted cert
/ HTTPS reverse proxy. To force plain HTTP (drop-pin only, no phone GPS), set
`TD_MOBILE_HTTP=1`. The "Drop pin" fallback always works without geolocation.

## Public SHARE mode (text a link, phone works anywhere)

Same Wi-Fi is fine on site, but for a phone on cellular use **share mode**: the
server is exposed over a Cloudflare quick tunnel and the crew opens a job from a
private **share link** — no Wi-Fi pairing, no public job list.

```
RUN_MOBILE_SHARE.bat
```

Needs `cloudflared` (`winget install --id Cloudflare.cloudflared`). It:

1. starts the server in **share-only public mode**,
2. opens a Cloudflare tunnel and prints a public `https://<name>.trycloudflare.com` URL,
3. with `--demo`, creates a demo job and prints a ready-to-send **share link**.

### How sharing works

- Each job has a random token. A share link is `<public-url>/join/<job_id>?token=<secret>`.
- Open the link on any phone → the job loads automatically (the token is stripped
  from the address bar after load). The **Audit tab** shows the share link + a QR
  to copy/scan for the rest of the crew.
- In public mode the start page **cannot create or browse jobs**. Job creation
  (demo/import) requires the **admin key** (`x-admin-key` header). Set a fixed key
  with `TD_MOBILE_ADMIN_KEY`, or the launcher prints a generated one.

### Modes at a glance

| Env | Behavior |
|---|---|
| (default) | Local HTTPS, same Wi-Fi/hotspot; start page can create jobs |
| `TD_MOBILE_HTTP=1` | Plain HTTP, drop-pin only |
| `TD_MOBILE_PUBLIC=1` | Share-only: no public creation/browse; admin-key to create |
| `TD_MOBILE_ADMIN_KEY=...` | Pin the admin key for creating jobs in public mode |
| `TD_MOBILE_PUBLIC_URL=...` | Origin used to build absolute share links (set by the tunnel launcher) |

### Privacy note

A Cloudflare quick tunnel routes job traffic through Cloudflare while in use, and
the laptop must stay running. For data that must never leave your machine, use
same-Wi-Fi mode. For an always-on URL without the laptop, deploy the backend to a
host (Render / Fly.io / VPS) — phase 2.

## Phone vs laptop

| Capability | Laptop | Phone (PWA) |
|---|---|---|
| Excel + .EST import | Local picker | Browser upload (same ingest) |
| Route build / optimize | Yes | Yes (server) |
| Map | Offline PMTiles | Online tiles |
| GPS capture | USB receiver | Phone browser geolocation |
| Drop pin fallback | Yes | Yes |
| Install / skip | Yes | Yes |
| Serial / lanes / dir / notes | Yes | Yes |
| PicoCount USB | Yes | No (counter columns blank) |
| Pickup | Yes | Yes |
| Audit / IG TFC export | Yes | Yes |
| Offline field mode | Yes | Not v1 (online-first) |
| Undo | Yes | Not yet |

## Architecture

- `mobile_web/server.py` — FastAPI app (REST + static PWA)
- `mobile_web/store.py` — web-safe JSON job store (token-scoped, in-memory cached)
- `mobile_web/tls.py` — self-signed LAN cert (secure context for phone GPS)
- `mobile_web/settings.py` — share-only public mode + admin key + public URL
- `mobile_web/static/` — the PWA (index.html, app.js, style.css, sw.js, manifest)
- `core/map_state.py` — Qt-free map payload shared with the renderer
- Reuses `core.ingest`, `core.routing`, `core.export` unchanged

### API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/jobs/demo` | Create job from bundled fixture (admin-key in public mode) |
| POST | `/api/jobs/import` | Upload Excel/CSV + .EST (admin-key in public mode) |
| GET | `/join/{id}?token=` | Share-link entry — serves the PWA, auto-opens the job |
| GET | `/api/jobs/{id}/share` | Share link for a job (token required) |
| GET | `/api/jobs/{id}/share.svg` | QR code (SVG) for the share link |
| GET | `/api/jobs/{id}` | Job + map state |
| GET | `/api/jobs/{id}/map-state` | Lean map payload |
| POST | `/api/jobs/{id}/route` | Optimize + trace |
| PATCH | `/api/jobs/{id}/stops/{uid}` | Edit fields / install / skip / pickup |
| POST | `/api/jobs/{id}/stops/{uid}/grab` | Save phone GPS / pin location |
| GET | `/api/jobs/{id}/audit` | Missing-field checklist |
| GET | `/api/jobs/{id}/export.csv` / `.xlsx` | IG TFC export |

All job routes require the job token (returned at create) via the `x-job-token`
header or `?token=` query.

## Tests

```
.venv\Scripts\python.exe scripts\mobile_user_prove.py     # user flow
.venv\Scripts\python.exe scripts\mobile_tls_prove.py      # real HTTPS secure context
.venv\Scripts\python.exe scripts\mobile_share_prove.py    # public share-only mode + links
.venv\Scripts\python.exe scripts\mobile_stress_loop.py    # load + latency
.venv\Scripts\python.exe scripts\mobile_app_check.py      # all + audit
```

The audit writes `logs/mobile_check/latest.md` (strengths / weaknesses /
improvements). Stress latency logs to `logs/mobile_stress/`.

## Known limits / next steps

- HTTPS is self-signed (one-time phone warning); use a trusted cert/proxy in prod
- Job token only, not full multi-user auth (phase 2)
- Online-first: no offline field queue yet (IndexedDB sync is phase 2)
- Heavy route builds (large jobs with a server road graph) should be backgrounded
- Browser/device E2E (Playwright) not wired; current proof is in-process API
