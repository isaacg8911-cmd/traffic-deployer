# Autonomous improve cycles (Forge)

Director asked for unattended learn-and-fix loops **inside app scope**. Each cycle:

1. `smoke_full.py` baseline  
2. Hunt: grep, preflight, counter sandbox, UX edge cases  
3. Minimal fix + smoke  
4. Optional `PROVE.bat` every N cycles  
5. Local commit when proven  

## Cycle log

| Cycle | Focus | Result |
|-------|--------|--------|
| 1 | Route pick dialog renumber after drag; PicoCount NAND @115200 before fast baud; PROVE step labels 1/6; closeEvent stops counter thread; export audit smoke | smoke PASS |
| 2 | PicoCount download proven COM10 **67,305 bytes** (nand_115200 path); v1.0.6 | sandbox --download OK |
| 3 | FTDI port preference; counter refresh auto-select; PICOCOUNT troubleshooting doc | smoke PASS |
| 4 | B2 fast preflight (`probe_counter=False` headless); B4 PyInstaller `dist/TrafficDeployer`; `UPDATE.bat`; `verify_portable.py`; stress loop + portable step | preflight 100/100; portable built |
| 5 | Preflight 100 desk (optional counter OK); `probe_port` tries all COM + busy message; Install tab auto-lists ports; GPS resume in `finally` | preflight 100/100 |
| 6 | **Simple mode** (`ui/simple_mode.py`): auto-optimize build, hide pick/wizard/strip; **P46** pages → `ui/pages/{setup,route,install}.py`; map sites-first + drive-leg blue; `main.py` 3740→3270 | smoke + stress `--full` PASS; Week13 68 stops |

## Not auto-fixed (needs field or sample data)

- Professional report from `.pcbin`  
- `main.py` further slim (target ≤1200 — handlers still in shell)  
- Download on cleared counter (empty study is correct behavior)
