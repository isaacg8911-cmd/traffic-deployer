# Traffic Deployer — Product Scope

**Director lock (DEMAND):** Only **two** delivery surfaces exist. Forge must not add or maintain others.

| Surface | What | Build / deploy | Prove |
|---------|------|----------------|-------|
| **Work laptop exe** | Offline California field desktop (PySide6, USB GPS, PicoCount) | Home PC: `BUILD_WORK_LAPTOP.bat` → `dist/TrafficDeployer-WorkLaptop.zip` | `VERIFY_WORK_LAPTOP.bat`, `SMOKE.bat`, `USER_PROVE.bat` |
| **Render web app** | Share-only hosted mobile PWA (`mobile_web/`) | `Dockerfile` + `render.yaml` on Render | `scripts/mobile_app_check.py`, `scripts/mobile_host_smoke.py` |

**Not products** (do not ship or document as versions): local LAN mobile server, Cloudflare tunnel laptop mode, Fly.io, standalone “portable” folder without work-laptop zip, source-only field installs.

Dev on home PC uses `START.bat` + Python to **build** the work-laptop exe — not a third field product.

## In scope (work laptop)

- Desktop offline California field tool (PySide6 + embedded map).
- Ingest Excel/CSV + `.EST`, multi-stop street routing, map trace.
- USB GPS live trace, install/pickup workflow, PicoCount 2500 USB, audit export.
- Local persistence (`tds_data/`), encrypted save.
- Offline road graph; see `ROUTING_AND_MAP.md`.
- Handover: `WORK_LAPTOP.md`.

## In scope (Render mobile)

- Share-link job open for crew phones; admin-key job creation only.
- Lean PWA: Route / Install / Pickup / Audit; phone geolocation.
- Deploy guide: `docs/MOBILE_HOST_DEPLOY.md`.

## Out of scope (propose before building)

- Third deployment targets or “modes” beyond the table above.
- Cloud sync / accounts for the desktop app.
- Regions beyond configured California offline map without Director approval.

## Architecture

- Shared business logic → `core/` / `road_router.py`; desktop shell = `main.py`.
- Desktop map/UI → `web/` + Qt bridge.
- Mobile host → `mobile_web/server.py` (FastAPI).
- Features ship with smoke or documented check in `HOW_TO_RUN.md` / mobile check.
