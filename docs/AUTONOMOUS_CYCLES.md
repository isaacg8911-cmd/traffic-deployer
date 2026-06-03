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

## Not auto-fixed (needs field or sample data)

- Professional report from `.pcbin`  
- `main.py` slim (P46)  
- Download on cleared counter (empty study is correct behavior)
