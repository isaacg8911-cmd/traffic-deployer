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

- Coworkers can open the public Render URL and import their own Excel/CSV + `.EST` files when `TD_MOBILE_OPEN_CREATE=1`.
- Each import creates a separate tokenized job (`/join/<job_id>?token=…`), so coworkers do not see or edit each other's files.
- Public start page cannot browse existing jobs.
- Each coworker manages their **own** job (revoke / extend / status) using its link token — equal use, no operator tier. The **admin key** (`x-admin-key`, generated `TD_MOBILE_ADMIN_KEY`) is an optional fallback (e.g. a lost phone).
- Share links can be revoked and expire (`TD_MOBILE_LINK_TTL_HOURS`). Manage with `scripts/manage_share_link.py` (admin) or from the phone (own token).

## Tabs (phone)

1. **Route** — ordered stops, build route, map trace (straight-line on host unless road graph uploaded).
2. **Install** — grab GPS or drop pin, install/skip per stop.
3. **Pickup** — mark secured, export.
4. **Audit** — shift summary, CSV export, share link + QR for crew.

## Local dev (Render image only)

Build and run the same Docker image locally — not a separate product:

```powershell
docker build -t td-mobile .
docker run -p 8800:8800 -e TD_MOBILE_PUBLIC=1 -e TD_MOBILE_OPEN_CREATE=1 td-mobile
```

Open `http://127.0.0.1:8800` (no TLS locally; Render terminates HTTPS in production).

## Proof artifacts

- `logs/mobile_check/latest.md` — strengths / weaknesses after `mobile_app_check.py`
- `logs/mobile_check/proofs/` — per-step JSON proofs
