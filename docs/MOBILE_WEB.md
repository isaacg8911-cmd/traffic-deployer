# Mobile Web (phone field runner)

A lean, online-first PWA companion to the desktop app. It reuses the desktop
core (ingest, routing, export) but drops USB GPS, the PicoCount workflow, and the
Qt shell. Location comes from the phone browser.

## Run it

```
RUN_MOBILE.bat
```

This starts the server and prints two URLs:

- On this PC: `http://127.0.0.1:8800`
- On phone: `http://<lan-ip>:8800` (same Wi-Fi)

Open the phone URL, then "Add to Home Screen" to install the app icon.

First request is slow (~2 min) the first time because the routing engine imports
osmnx on startup; after that it is fast.

### Geolocation note

Phone browser geolocation needs a **secure context**. It works on `localhost`,
but over LAN by IP the browser blocks `getCurrentPosition` unless the page is
HTTPS. For real field use, host the server behind an HTTPS reverse proxy (or a
tunnel). The "Drop pin" fallback works without geolocation.

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
- `mobile_web/static/` — the PWA (index.html, app.js, style.css, sw.js, manifest)
- `core/map_state.py` — Qt-free map payload shared with the renderer
- Reuses `core.ingest`, `core.routing`, `core.export` unchanged

### API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/jobs/demo` | Create job from bundled fixture |
| POST | `/api/jobs/import` | Upload Excel/CSV + .EST |
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
.venv\Scripts\python.exe scripts\mobile_stress_loop.py    # load + latency
.venv\Scripts\python.exe scripts\mobile_app_check.py      # both + audit
```

The audit writes `logs/mobile_check/latest.md` (strengths / weaknesses /
improvements). Stress latency logs to `logs/mobile_stress/`.

## Known limits / next steps

- Job token only, not full multi-user auth (phase 2)
- Online-first: no offline field queue yet (IndexedDB sync is phase 2)
- Heavy route builds (large jobs with a server road graph) should be backgrounded
- Browser/device E2E (Playwright) not wired; current proof is in-process API
