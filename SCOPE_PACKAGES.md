# Traffic Deployer ΓÇö Scope packages

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
| P8 | **Demo workflow proof** | Headless ingest → route → export regression. | `scripts\demo_workflow.py` |
| P9 | **Driving nav** | Turn banner, voice, off-route reroute + voice. | smoke voice + `START.bat` drive |
| P10 | **Routing quality** | Segment matrix + 2-opt + return-home trace. | `demo_workflow.py` route returns home |
| P11 | **Map & trace UX** | Crossing dots, badges, day filter, follow-me. | smoke web + map |
| P12 | **Install field polish** | Grab GPS street, wide-street warn on Install. | smoke + install path |
| P13 | **Setup / offline gate** | READY FOR OFFLINE checklist blocks/warns. | smoke offline_gate |
| P14 | **PROVE.bat** | One double-click: smoke + demo + preflight. | `PROVE.bat` exit 0 |
| P15 | **main.py slim** | Threads + web page + paths in `ui/`; zero behavior change. | `PROVE.bat` |

**Shipped (2026-06-01):** P6ΓÇôP15.

| ID | Name | One-line scope | Prove with |
|----|------|----------------|------------|
| P16 | **Route perf (matrix)** | Batched road matrix Γëñ100 stops; matrix 2-opt only (no graph-refine Dijkstra loop). | `scripts/benchmark_route.py` |
| P18 | **Route perf (trace)** | Route build polylines without turn_by_turn; driving still uses `leg_plan`. | smoke + benchmark |

**Shipped (2026-06-02):** P16, P18 (Director bundle 1+2+3+4).

| ID | Name | One-line scope | Prove with |
|----|------|----------------|------------|
| P19 | **Route quality v2** | Exact matrix Γëñ9, Or-opt, cached crossing 2-opt + side polish; preserve optimized crossings on trace. | `benchmark_route.py` + smoke |

**Shipped (2026-06-02):** P19 (route quality v2).

| ID | Name | One-line scope | Prove with |
|----|------|----------------|------------|
| P20 | **Far anchor routing** | Stop **#1 = farthest from home** (road miles); zones farΓåÆnear; open-path within zone (no home-depot 2-opt). | `START.bat` + rebuild; badge 1 on NW/E fringe |
| P21 | **Bigger zones only** | Coarser grid (P20 logic); no flat TSP for 12+. | benchmark + field map |
| P22 | **Miles-first (legacy)** | Revert to flat matrix TSP (min miles, may backtrack). | benchmark |
| P23 | **Map: zone hints** | Optional zone tint or debug ΓÇ£Zone AΓÇ¥ in Route list. | smoke web |
| P24 | **Home sanity check** | Block/warn build if home is default but stops are 30+ mi away. | smoke validate |

**Pick one line, combo (e.g. `P20`), or `none` + your words.**

**Shipped (2026-06-02):** P20ΓÇôP21 routing; P24 home check; address search (CA bias + pick list).

| ID | Name | One-line scope | Prove with |
|----|------|----------------|------------|
| P25 | **Workflow strip** | Setup step indicator (Start ΓåÆ Files ΓåÆ Road ΓåÆ Build ΓåÆ Drive). | `START.bat` Setup tab |
| P26 | **Setup sections** | Card sections: origin, files, build, GPS/offline. | `START.bat` |
| P27 | **Route command center** | Stat cards + Drive / Map / Stop list groups. | `START.bat` Route tab |
| P28 | **Visual identity** | Navy/amber theme, nav rail, placeholder polish. | `START.bat` themes |

**Shipped (2026-06-02):** P25ΓÇôP28 UI bundle A (Director).

| ID | Name | One-line scope | Prove with |
|----|------|----------------|------------|
| P32 | **Setup network panel** | In-app Test home WiΓÇæFi (map, graph, Overpass, geocode). | `START.bat` Setup |
| P33 | **Home checklist** | Setup checklist + block READY FOR OFFLINE until start/files/graph/build. | smoke + Setup |
| P23 | **Map zone hints** | Zone colors on segment lines + Z on badges. | `START.bat` map |
| P35 | **Route trust** | Post-build summary line + `golden_routes.py` bands. | `scripts/golden_routes.py` |
| P36 | **Field bar + map recover** | GPS/mode strip, Recover map button. | `START.bat` |
| ΓÇö | **Saved home** | Last geocoded address stored in profile. | smoke persistence |
| ΓÇö | **Offline contract** | `offline_policy` + `OFFLINE_CONTRACT.md` + tests. | `test_offline_session.py` |

**Shipped (2026-06-02):** P32ΓÇôP36 Phase 1 trust/offline bundle.

| ID | Name | One-line scope | Prove with |
|----|------|----------------|------------|
| P37 | **Setup wizard** | 3-step Quick setup wizard on Setup tab. | `START.bat` Setup |
| P38 | **Manual route order** | Move stop up/down + re-trace only (no re-optimize). | smoke + Route tab |
| P39 | **Install photo** | Local install photo per stop in `tds_data/field_photos/`. | smoke persistence |
| P40 | **Shift summary** | End-of-day summary on Audit tab. | `smoke_full` shift_summary |
| P41 | **Field strip++** | Route strip shows next-stop distance. | `START.bat` Route |
| P42 | **main.py slim (pages)** | Audit + Pickup pages in `ui/pages/`. | `PROVE.bat` |
| P43 | **Portable build** | `traffic_deployer.spec` + `scripts/build_portable.ps1`. | build script |
| P44 | **PROVE full** | smoke + demo + preflight + golden + benchmark. | `PROVE.bat` |
| P45 | **OR-Tools optional** | TSP 10ΓÇô15 stops when `ortools` installed. | benchmark |
| ΓÇö | **GPS heading** | Slightly smoother heading buffer (16 samples). | field GPS |

**Shipped (2026-06-02):** P37ΓÇôP45 Phases 2ΓÇô4 operator polish + packaging + routing bounds.

| ID | Name | One-line scope | Prove with |
|----|------|----------------|------------|
| P46 | **main.py slim v2** | Move wiring to `ui/`; **main.py Γëñ1200 lines**; zero behavior change. | `PROVE.bat` exit 0 |

**Director freeze:** Prefer **P46** or **P3** before new feature IDs unless Director ends freeze (`DEMAND:` or `P7` off).

| ID | Name | One-line scope | Prove with |
|----|------|----------------|------------|
| P47 | **PicoCount enterprise** | Field readiness + export columns + shift summary + download buffer fix + status chips | `smoke_full` + `picocount_sandbox.py` |
| P48 | **Enterprise chrome** | Counter/pickup/audit panels, scrollbars, v1.0.5 identity | `START.bat` visual |
| P49 | **Route pick order window** | Floating reorder list during map pick | smoke + Route tab |
| P50 | **Tomorrow proof kit** | `docs/TOMORROW_MORNING.md` + PROVE step 6 sandbox | `PROVE.bat` |

**Shipped (2026-06-03 overnight):** P47ΓÇôP50 + `core/map_display.py` tracked; routing crossing polish (ZONE_MIN 8).

**Modes:** `explore` | `build` | `ship`
