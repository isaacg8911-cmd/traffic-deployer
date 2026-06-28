# Always-on mobile host (no laptop required)

The Cloudflare tunnel (`RUN_MOBILE_SHARE.bat`) needs your laptop on for the
share link to work. This guide puts the **same** mobile backend on an always-on
host so a share link works 24/7 — text it once, the crew opens it any time.

It serves the identical FastAPI app (`mobile_web.server`) in share-only public
mode, just on a hosted box instead of your laptop.

---

## What you sign up for (pick one)

- **Render** (recommended, simplest): https://render.com — connect this GitHub
  repo, it reads `render.yaml`, builds the `Dockerfile`, done.
- **Fly.io** (alternative): https://fly.io — `flyctl` + `deploy/fly.toml`.

Both terminate HTTPS for you (the share link is `https://…`), so there's no cert
warning like the LAN mode has.

---

## Option A — Render (recommended)

1. Push this branch to GitHub (if not already): the repo must contain
   `Dockerfile` and `render.yaml` at the root (they're here).
2. Render → **New → Blueprint** → pick this repo → **Apply**.
   - It creates a Docker web service from `render.yaml`.
   - Plan `starter` includes a 1 GB persistent disk at `/app/tds_data` so jobs
     survive restarts. The free plan works too but has **no disk** (jobs are lost
     when the instance sleeps).
3. When it's live, open the service → **Environment** and copy the generated
   **`TD_MOBILE_ADMIN_KEY`** (this is your "create jobs" key; the crew never needs it).
4. Your public URL is `https://<service-name>.onrender.com`.

### Create a job + get the share link

The phone start page can't create jobs in public mode (by design). Create from
your laptop using the admin key:

```
# bundled demo job (no files needed) — returns a ready share_url
curl -X POST https://<service>.onrender.com/api/jobs/demo -H "x-admin-key: <KEY>"
```

For a real job, POST your Excel/CSV + `.EST` files to `/api/jobs/import` with the
same `x-admin-key` header (multipart fields: `home_lat`, `home_lon`, `excel`,
`est`; optional `expires_in_hours`). The JSON response includes `share_url` —
text that to the crew.

> Tip: `RUN_MOBILE_SHARE.bat --demo` already prints a share link for the tunnel
> path; for the hosted path use the curl above or `scripts/mobile_host_smoke.py`.

---

## Option B — Fly.io

From the repo root (Dockerfile is reused):

```
fly launch --no-deploy --copy-config --name traffic-deployer-mobile
fly volume create tds_data --size 1
fly secrets set TD_MOBILE_ADMIN_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(18))")
fly deploy
```

Public URL: `https://traffic-deployer-mobile.fly.dev`. Create jobs the same way
as Render (admin key header).

---

## Verify a live deploy

Run the deploy smoke against your URL — same checks the in-process proof runs,
but over real HTTP:

```
python scripts/mobile_host_smoke.py --url https://<service>.onrender.com --admin-key <KEY>
```

Green = public mode on, creation gated, share link opens the job, revoke/extend work.

---

## Manage share links (lost phone / end of shift)

From your laptop, against the live host:

```
# cut off a lost phone's link
python scripts/manage_share_link.py revoke <id-or-link> --url https://<service>.onrender.com --admin-key <KEY>

# give a link 8 more hours
python scripts/manage_share_link.py extend <id-or-link> --hours 8 --url https://<service>.onrender.com --admin-key <KEY>

# never expire (also un-revokes)
python scripts/manage_share_link.py extend <id-or-link> --hours 0 --url ... --admin-key <KEY>

# check state
python scripts/manage_share_link.py status <id-or-link> --url ... --admin-key <KEY>
```

`TD_MOBILE_LINK_TTL_HOURS` (set to `16` in `render.yaml`) makes every new link
self-expire after a shift; per-job `expires_in_hours` overrides it at creation.

---

## Environment variables

| Var | Meaning |
|-----|---------|
| `TD_MOBILE_PUBLIC=1` | Share-only public mode (set by image/blueprint). |
| `TD_MOBILE_ADMIN_KEY` | Key required to create jobs. Render generates it; on Fly set it as a secret. |
| `TD_MOBILE_LINK_TTL_HOURS` | Default link lifetime in hours. `0`/unset = never expire. |
| `TD_MOBILE_PUBLIC_URL` | Optional. Pin the public origin for share links. Usually unneeded — `--proxy-headers` derives `https://<host>` from the platform edge. |
| `TD_MOBILE_TILE_URL` / `_ATTRIB` | Optional keyed basemap tiles. |

---

## Honest limits

- **Data leaves your machine.** Hosted means job data (site coords, installs)
  lives on Render/Fly. For data that must never leave your laptop, use same-Wi-Fi
  mode (`RUN_MOBILE.bat`) instead.
- **Free tiers sleep.** A free instance cold-starts on first hit (a few seconds)
  and, without a disk, loses jobs on restart. Use the `starter`/volume plan for a
  real shift.
- **Routing is straight-line on the host** unless a road graph is bundled — the
  hosted image ships without `osmnx`/`road_graph.graphml` to stay small. Build the
  route on the laptop app if you need street-traced miles, or add the graph file
  to the image later.
- Still single-credential per job (token in the link). Revoke/expiry mitigate a
  lost phone; full multi-user auth is a later phase.
