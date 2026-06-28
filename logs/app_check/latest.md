# App check — user

- **When:** 2026-06-28T07:17:10Z
- **Result:** PASS
- **Duration:** 83.3s

## Steps

- [OK] `drop_pin_enter` — 23.1s
- [OK] `manual_grab_site` — 20.3s
- [OK] `install_no_block` — 17.9s
- [OK] `install_drop_pin_desk` — 2.5s
- [OK] `map_bridge` — 1.2s
- [OK] `ui_wiring` — 2.1s
- [OK] `demo_workflow` — 7.5s
- [OK] `field_sim` — 8.7s

## Strengths

- Drop pin enter: map stays responsive; no corner pin before click
- Manual grab site 15228: bridge click saves segment midpoint + screenshot artifact
- INSTALL advisory checklist: site can install without GPS pin or counter clear
- Drop pin + offline geocode + install commit covered in desk simulation
- Map bridge: tdmap URL parse, AppWebPage handler, fireMapClick bridge-first wiring
- UI wiring audit: 52+ click targets connected to handlers
- Field sim: bundled job ingest → route → install → audit export pipeline

## Weaknesses

- Drop pin enter: stale map marker may remain visible before click (markerCount=1) — cosmetic, not blocking

## Improvements / gaps

- Clear non-field markers when entering manual grab / drop pin mode
- Coverage gap: Route pick dialog drag/reorder — static wiring only, no live GUI reorder proof
- Coverage gap: Pickup tab end-of-shift flow — field_sim covers export, not full pickup UI
- Coverage gap: FOLLOW GPS / compass while driving — wiring audit only
- Coverage gap: Offline tile render — preflight checks files, not WebGL frame
- Coverage gap: PicoCount USB — optional picocount_sandbox; hardware Isaac-only
- Coverage gap: Multi-day map filter (Map on screen) — not exercised in user proofs
- Re-run USER_PROVE.bat after any Install/Route/Map UI change before ship
