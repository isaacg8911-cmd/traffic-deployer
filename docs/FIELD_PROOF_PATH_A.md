# Path A field proof — traffic-deployer

Claude-reviewed field-proof plan (advisory `d4c60204ff4e`, graded `caught_risk`). Use this before calling the app field-ready or starting E2/E3/E4 cleanup.

**Director ritual:** [FIELD_PROOF_RITUAL.md](../../../docs/FIELD_PROOF_RITUAL.md) · work laptop: [FIELD_PROOF_WORK_LAPTOP.md](../../../docs/FIELD_PROOF_WORK_LAPTOP.md)  
**Morning checklist:** [TOMORROW_MORNING.md](TOMORROW_MORNING.md)

---

## Sequence (locked)

1. **Path A field proof** — July focus; prove real-world readiness first.
2. **Re-run `PROVE.bat`** — confirm baseline after any field fixes.
3. **Then cleanup** — E2 (ship gate) → E3 (core/ui boundary) → E4 (scope catalog), one package per session, full `PROVE.bat` after each.

E2/E3/E4 defer until field proof (Claude advisory `555c9648003e`): cleanup would contaminate the P46 proof baseline and does not move Path A closer to the field.

---

## Field-ready gates (Forge must prove)

| Gate | Why | Existing proof | Gap |
|------|-----|--------------|-----|
| Import → route correctness | Wrong route in field has real cost | `test_field_sim.py`, `demo_workflow.py` | Add malformed/empty Excel, CSV, EST cases with clean error, no silent route |
| Offline contract | No network in field mode | `test_offline_session.py`, `OFFLINE_CONTRACT.md` | Keep in PROVE chain; extend if new geo/connectivity entry points appear |
| GPS degraded mode | Stale fix / signal loss must not hang or lie | Manual field proof | Add scripted stale-fix injection or documented degraded behavior test |
| Crash / restart mid-job | Resume must not duplicate or drop stops | `smoke_full` persistence checks | Add forced-kill + reload mid install/pickup scenario |
| PicoCount boundary | Hardware disconnect, debounce, manual override | `picocount_sandbox.py` (optional COM) | Document manual override path; prove disconnect/reconnect when COM available |
| Export integrity | Partial export must not look complete | `smoke_full` export paths | Add kill-during-export + low-disk export failure cases |
| Setup checklist | Block READY FOR OFFLINE until safe | `test_offline_session.py`, setup checklist eval in `test_field_sim.py` | Align with TOMORROW_MORNING pass criteria |

**Field-ready** = all scripted gates green **plus** Director Path A paste with `outdoor: yes`.

---

## Forge DEMAND (app workspace)

Open `projects/traffic-deployer` (not OS root). One session:

```text
DEMAND: Path A field-proof gates — extend PROVE chain with Claude-reviewed failure paths; no E2/E3/E4 until green

Scope:
1. Add scripted checks (or document existing coverage) for:
   - malformed/empty/partial Excel, CSV, EST → visible error, no route built
   - forced app kill + restart mid install/pickup → state reloads, no duplicate/dropped stops
   - export interrupted (kill during write) → no half-valid export accepted
   - low-disk / storage-full during export → fails loudly, prior data intact
2. Wire new checks into PROVE.bat or APP_CHECK.bat tier (document in HOW_TO_RUN.md).
3. Confirm test_offline_session.py stays in proof chain for field-mode network assertion.
4. Do NOT start E2, E3, or E4 in this session.

Prove:
- PROVE.bat exit 0
- New failure-path tests exit 0 (or list which remain manual-only with reason)
- main.py line count unchanged unless bugfix required
- [Cursor Log] with advisory refs d4c60204ff4e, 555c9648003e
```

---

## Director paste (after outdoor session)

```text
FIELD-PROOF: YYYY-MM-DD app=traffic-deployer path=A machine=work version=<title bar>
pass: home, build, gps, export
outdoor: yes
fail: <one line each, or none>
feel: <glare, gloves, voice, map — one line>
trust: yes / no / with_fixes
```

---

## Wait until after field proof

- UI/cosmetic work beyond P46
- Route-algorithm performance tuning
- New import formats or integrations
- E2 ship-gate dedup, E3 core/ui boundary, E4 scope catalog hygiene
- Replacing human GPS sanity check on first live job

---

_Advisory source: MindLink Claude lane, sanitized product context only — no client/job data._
