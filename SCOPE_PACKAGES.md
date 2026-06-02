# Traffic Deployer — Scope packages

Director-approved bundles. Forge lists these in `build` / `ship` menus.

| ID | Name | One-line scope | Prove with |
|----|------|----------------|------------|
| P1 | **Routing proof** | Route order + polylines + routing math only; no UI/tab changes. | `.venv\Scripts\python.exe scripts\smoke_full.py` |
| P2 | **Map/GPS field pass** | Live trace, map bridge, install GPS grab; no routing graph changes. | `START.bat` + smoke web/server |
| P3 | **Ship check** | Smoke green + HOW_TO_RUN note if needed; no new features. | `SMOKE.bat` or `scripts\smoke_test.ps1` |
| P4 | **Core extract (safe)** | Move logic to `core/`; zero behavior change. | smoke before/after |
| P5 | **Docs only** | README / HOW_TO_RUN / ROUTING_AND_MAP; no code behavior change. | review |
| P6 | **Graph & export guards** | `has_graph`/load truth, excel errors, smoke path. | `SMOKE.bat` |
| P7 | **Work-laptop network kit** | `diagnose_network.py`, import graphml UX. | `diagnose_network.py` |
| P8 | **Boss demo lane** | `DEMO_FOR_BOSS.md` + demo workflow. | `scripts\demo_workflow.py` |
| P9 | **Driving nav** | Turn banner, voice, off-route reroute + voice. | smoke voice + `START.bat` drive |
| P10 | **Routing quality** | Segment matrix + 2-opt + return-home trace. | `demo_workflow.py` route returns home |
| P11 | **Map & trace UX** | Crossing dots, badges, day filter, follow-me. | smoke web + map |
| P12 | **Install field polish** | Grab GPS street, wide-street warn on Install. | smoke + install path |
| P13 | **Setup / offline gate** | READY FOR OFFLINE checklist blocks/warns. | smoke offline_gate |
| P14 | **PROVE.bat** | One double-click: smoke + demo + preflight. | `PROVE.bat` exit 0 |
| P15 | **main.py slim** | Threads + web page + paths in `ui/`; zero behavior change. | `PROVE.bat` |

**Shipped (2026-06-01):** P6–P15.

**Modes:** `explore` | `build` | `ship`
