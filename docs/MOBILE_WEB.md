# Mobile Web (Render — phone field runner)

Online-first PWA on **Render** only. Reuses desktop `core/` (ingest, routing, export) without Qt, USB GPS, or PicoCount. Location comes from the phone browser.

**Deploy:** see **[MOBILE_HOST_DEPLOY.md](MOBILE_HOST_DEPLOY.md)** (`Dockerfile` + `render.yaml`).

**Do not** run a separate local/LAN/tunnel mobile server — that path was removed. Prove changes with:

```powershell
.venv\Scripts\python.exe scripts\mobile_app_check.py
```

Against a live deploy:

```powershell
.venv\Scripts\python.exe scripts\mobile_host_smoke.py --url https://<service>.onrender.com --admin-key <KEY>
```

## How sharing works

- Crew opens jobs via **share link** only (`/join/<job_id>?token=…`).
- Public start page cannot create or browse jobs.
- Job creation (demo/import) requires **admin key** (`x-admin-key` header). Render generates `TD_MOBILE_ADMIN_KEY`.
- Share links can be revoked and expire (`TD_MOBILE_LINK_TTL_HOURS`). Manage with `scripts/manage_share_link.py`.

## Tabs (phone)

1. **Route** — ordered stops, build route, map trace (straight-line on host unless road graph uploaded).
2. **Install** — grab GPS or drop pin, install/skip per stop.
3. **Pickup** — mark secured, export.
4. **Audit** — shift summary, CSV export, share link + QR for crew.

## Local dev (Render image only)

Build and run the same Docker image locally — not a separate product:

```powershell
docker build -t td-mobile .
docker run -p 8800:8800 -e TD_MOBILE_PUBLIC=1 td-mobile
```

Open `http://127.0.0.1:8800` (no TLS locally; Render terminates HTTPS in production).

## Proof artifacts

- `logs/mobile_check/latest.md` — strengths / weaknesses after `mobile_app_check.py`
- `logs/mobile_check/proofs/` — per-step JSON proofs
