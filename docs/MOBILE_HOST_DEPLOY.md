# Render mobile host (always-on share links)

The **only** hosted mobile surface. Puts `mobile_web.server` on Render so crew share links work 24/7 without your laptop.

---

## Deploy on Render

1. Push this repo to GitHub (`Dockerfile` + `render.yaml` at root).
2. Render → **New → Blueprint** → pick repo → **Apply**.
   - Creates Docker web service from `render.yaml`.
   - `starter` plan includes 1 GB disk at `/app/tds_data` (jobs survive restarts).
3. When live, copy **`TD_MOBILE_ADMIN_KEY`** from Environment (crew never needs it).
4. Public URL: `https://<service-name>.onrender.com`.

### Create a job + share link

Phones cannot create jobs in public mode. From your laptop:

```bash
curl -X POST https://<service>.onrender.com/api/jobs/demo -H "x-admin-key: <KEY>"
```

Real job: `POST /api/jobs/import` with `x-admin-key`, multipart `home_lat`, `home_lon`, `excel`, `est`. Response includes `share_url`.

---

## Verify live deploy

```powershell
.venv\Scripts\python.exe scripts\mobile_host_smoke.py --url https://<service>.onrender.com --admin-key <KEY>
```

Full live prove:

```powershell
.venv\Scripts\python.exe scripts\mobile_live_host_prove.py --url https://<service>.onrender.com --admin-key <KEY>
```

---

## Manage share links

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
| `TD_MOBILE_PUBLIC=1` | Share-only public mode (blueprint default). |
| `TD_MOBILE_ADMIN_KEY` | Required to create jobs. Render generates it. |
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
