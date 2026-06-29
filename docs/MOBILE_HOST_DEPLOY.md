# Render mobile host (self-serve mobile jobs)

The **only** hosted mobile surface. Puts `mobile_web.server` on Render so coworkers can import their own files and crew share links work 24/7 without your laptop.

---

## Deploy on Render

1. Push this repo to GitHub (`Dockerfile` + `render.yaml` at root).
2. Render → **New → Blueprint** → pick repo → **Apply**.
   - Creates Docker web service from `render.yaml`.
   - `starter` plan includes 1 GB disk at `/app/tds_data` (jobs survive restarts).
3. When live, copy **`TD_MOBILE_ADMIN_KEY`** from Environment (crew never needs it).
4. Public URL: `https://<service-name>.onrender.com`.
5. Send coworkers the public URL. They import their own Excel/CSV + `.EST` files; each import creates a separate tokenized job and share link.

### Coworker self-serve import

With `TD_MOBILE_OPEN_CREATE=1`, a coworker opens the public URL and imports their own files from the start screen:

1. Open `https://<service-name>.onrender.com`.
2. Choose one or more Excel/CSV files and one or more `.EST` files.
3. Tap **Import job**.
4. Use the generated job on that phone, or copy the share link/QR from Audit.

Each job is stored separately and still requires its secret `/join/<job_id>?token=...` link to reopen or share.

### Admin-create a job + share link

The admin key still works for operator-created jobs:

```bash
curl -X POST https://<service>.onrender.com/api/jobs/demo -H "x-admin-key: <KEY>"
```

Real job: `POST /api/jobs/import` with `x-admin-key`, multipart `home_lat`, `home_lon`, `excel`, `est`. Response includes `share_url`.

---

## Verify live deploy

```powershell
.venv\Scripts\python.exe scripts\mobile_host_smoke.py --url https://<service>.onrender.com --admin-key <KEY> --open-create
```

Full live prove:

```powershell
.venv\Scripts\python.exe scripts\mobile_live_host_prove.py --base https://<service>.onrender.com --admin-key <KEY> --open-create
```

---

## Manage share links

Each coworker can revoke/extend/status their **own** job from the phone (the app uses its link token). The admin key is only needed to manage a job you don't hold the link for (e.g. a lost phone):

```powershell
.venv\Scripts\python.exe scripts\manage_share_link.py revoke <id-or-link> --url https://<service>.onrender.com --admin-key <KEY>
.venv\Scripts\python.exe scripts\manage_share_link.py extend <id-or-link> --hours 8 --url https://<service>.onrender.com --admin-key <KEY>
.venv\Scripts\python.exe scripts\manage_share_link.py status <id-or-link> --url https://<service>.onrender.com --admin-key <KEY>
```

`TD_MOBILE_LINK_TTL_HOURS` (16 in `render.yaml`) self-expires links after a shift.

---

## Environment variables

| Var | Meaning |
|-----|---------|
| `TD_MOBILE_PUBLIC=1` | Public internet mode. |
| `TD_MOBILE_OPEN_CREATE=1` | Allows coworkers to import their own files from the public start screen. |
| `TD_MOBILE_ADMIN_KEY` | Optional fallback for managing a job without its link token (e.g. a lost phone). Coworkers normally manage their own job via its link. Render generates it. |
| `TD_MOBILE_LINK_TTL_HOURS` | Default link lifetime. `0` = never expire. |
| `TD_MOBILE_PUBLIC_URL` | Optional pinned origin for share links. |
| `TD_MOBILE_TILE_URL` / `_ATTRIB` | Optional keyed basemap tiles. |

---

## Limits

- **Data on Render.** Job coords/installs live on the host — not for data that must never leave your machine (use work-laptop exe).
- **Free tier sleeps** and loses jobs without disk. Use `starter` + volume for real shifts.
- **Straight-line routing** on host unless road graph is added to the image.
- Single worker + persistent disk for production shifts.

See also: **[MOBILE_WEB.md](MOBILE_WEB.md)** · **SCOPE.md** (two products only).
