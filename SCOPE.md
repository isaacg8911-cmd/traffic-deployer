# Traffic Deployer — Product Scope

## In scope

- Desktop offline California field tool (PySide6 + embedded map).
- Ingest Excel/CSV + `.EST`, multi-stop street routing, map trace.
- USB GPS live trace, install/pickup workflow, audit export.
- Local persistence (`tds_data/`), encrypted save, `START.bat` workflow.
- Offline road graph; see `ROUTING_AND_MAP.md`.
- Smoke: `scripts/smoke_full.py`, `SMOKE.bat`.

## Out of scope (propose before building)

- Cloud sync, accounts, multi-user backend.
- Regions beyond configured California offline map without Director approval.
- Reordering field workflow tabs without Director approval.
- Unrelated product domains.

## Architecture

- Business logic → `core/` / `road_router.py`; keep `main.py` as shell/wiring.
- Map/UI → `web/` + Qt bridge.
- Features ship with smoke or documented check in `HOW_TO_RUN.md`.
