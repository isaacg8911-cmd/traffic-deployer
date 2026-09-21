"""Mobile web lane for Traffic Deployer.

A FastAPI + PWA companion that reuses the desktop core (ingest, routing,
export) but drops USB GPS, PicoCount, and the Qt shell. Same field tabs as
the laptop. If the server cannot save, the phone keeps a local snapshot and
a portable `.tdjob.json` file. See docs/MOBILE_WEB.md.
"""
