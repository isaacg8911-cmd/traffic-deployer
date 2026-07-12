"""Prove RouteOptimizeThread.start() is not shadowed (BUILD ROUTE field path).

Regression: naming the GPS arg `self.start` overwrote QThread.start →
TypeError: 'NoneType' object is not callable when BUILD ROUTE ran without GPS.
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("TDS_WORK_LAPTOP", "1")

from core.hardware_profile import apply_webengine_env  # noqa: E402

apply_webengine_env()


def main() -> int:
    print("BUILD ROUTE THREAD — QThread.start shadow regression\n")
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication

    from core import ingest, routing
    from field_job_fixtures import resolve_field_job
    from ui.paths import DATA_DIR
    from ui.threads import RouteOptimizeThread
    import road_router

    app = QApplication.instance() or QApplication(sys.argv)

    job = resolve_field_job()
    sites = ingest.parse_excel_sites([job.xls])
    stops = ingest.match_est_files(
        [{"path": p, "label": lab} for p, lab in job.ests], sites, job.home)
    if len(stops) < 2:
        print(f"FAIL need >=2 stops, got {len(stops)}")
        return 1
    if not road_router.has_graph(DATA_DIR):
        print(f"FAIL no road graph in {DATA_DIR}")
        return 1

    thread = RouteOptimizeThread(list(stops), tuple(job.home), DATA_DIR, start=None)
    if not callable(getattr(thread, "start", None)):
        print("FAIL thread.start is not callable (still shadowed)")
        return 1
    print("  OK  thread.start callable")

    result: dict = {}

    def on_done(res: dict) -> None:
        result.update(res)

    thread.finished_result.connect(on_done)
    thread.start()
    t0 = time.perf_counter()
    while thread.isRunning() and time.perf_counter() - t0 < 120:
        app.processEvents()
        time.sleep(0.05)
    for _ in range(40):
        app.processEvents()
        time.sleep(0.02)

    if thread.isRunning():
        print("FAIL optimize thread hung")
        thread.requestInterruption()
        thread.wait(3000)
        return 1
    if not result.get("ok"):
        print(f"FAIL optimize result: {result}")
        return 1
    miles = float((result.get("route") or {}).get("miles") or 0)
    n = len(result.get("order") or [])
    print(f"  OK  optimize+trace — {n} stops, {miles:.1f} mi")
    if miles <= 0 or n < 2:
        print("FAIL empty route")
        return 1
    # Sanity vs direct call
    direct = routing.build_route(result["order"], job.home, DATA_DIR)
    print(f"  OK  direct build_route {direct.get('miles', 0):.1f} mi")
    print("\nBUILD ROUTE THREAD PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
