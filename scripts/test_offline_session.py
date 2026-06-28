"""Assert field mode performs no public HTTP (offline contract).

    .venv\\Scripts\\python.exe scripts\\test_offline_session.py
"""
from __future__ import annotations

from contextlib import contextmanager
import os
import sys
from typing import Iterator

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATA = os.path.join(ROOT, "tds_data")
APP = ROOT


@contextmanager
def forbid_public_http() -> Iterator[list[str]]:
    """Record any public HTTP attempt; localhost remains allowed for map assets."""
    import urllib.request

    calls: list[str] = []
    original_urlopen = urllib.request.urlopen
    original_requests_get = None
    requests_mod = None
    try:
        import requests as requests_mod  # type: ignore[no-redef]

        original_requests_get = requests_mod.get
    except Exception:
        requests_mod = None

    def _is_local(url: str) -> bool:
        return (
            url.startswith("http://127.0.0.1:")
            or url.startswith("http://localhost:")
            or url.startswith("https://127.0.0.1:")
            or url.startswith("https://localhost:")
        )

    def guarded_urlopen(req, *args, **kwargs):  # noqa: ANN001, ANN202
        url = getattr(req, "full_url", req)
        url = str(url)
        calls.append(url)
        if not _is_local(url):
            raise RuntimeError(f"public HTTP blocked in field-mode proof: {url}")
        return original_urlopen(req, *args, **kwargs)

    urllib.request.urlopen = guarded_urlopen
    if requests_mod is not None and original_requests_get is not None:

        def guarded_requests_get(url, *args, **kwargs):  # noqa: ANN001, ANN202
            url = str(url)
            calls.append(url)
            if not _is_local(url):
                raise RuntimeError(f"public HTTP blocked in field-mode proof: {url}")
            return original_requests_get(url, *args, **kwargs)

        requests_mod.get = guarded_requests_get
    try:
        yield calls
    finally:
        urllib.request.urlopen = original_urlopen
        if requests_mod is not None and original_requests_get is not None:
            requests_mod.get = original_requests_get


def test_core_offline_session_contract() -> None:
    from core import connectivity, geo, offline_policy, setup_network

    offline_policy.set_field_mode(True)
    try:
        if geo.geocode_candidates("1 Main St, Garden Grove, CA"):
            raise AssertionError("geocode should return empty in field mode")
        if geo.street_from_coords(33.77, -117.94):
            raise AssertionError("reverse geocode should be empty in field mode")
        if connectivity.geocode_hosts_reachable() is not None:
            raise AssertionError("connectivity probe should be skipped in field mode")
        rows = setup_network.run_checks(data_dir=DATA, app_dir=APP)
        if not rows or "Field mode" not in rows[0].get("label", ""):
            raise AssertionError("setup_network should skip external tests in field mode")
    finally:
        offline_policy.set_field_mode(False)


def test_split_field_mode_blocks_public_http() -> None:
    from core import connectivity, geo, offline_policy, setup_network
    from ui.shell.field_mode import FieldModeMixin

    class DummyState:
        offline_mode = True

    class DummyWindow(FieldModeMixin):
        state = DummyState()

    win = DummyWindow()
    try:
        win._sync_field_mode()
        if not offline_policy.field_mode():
            raise AssertionError("FieldModeMixin did not enable core offline policy")
        if win._internet_allowed():
            raise AssertionError("FieldModeMixin allowed internet while offline_mode=True")
        with forbid_public_http() as calls:
            geo.geocode_candidates("1 Main St, Garden Grove, CA")
            geo.street_from_coords(33.77, -117.94)
            connectivity.geocode_hosts_reachable()
            setup_network.run_checks(data_dir=DATA, app_dir=APP)
        if calls:
            raise AssertionError(f"field-mode UI/core path attempted public HTTP: {calls}")
    finally:
        win.state.offline_mode = False
        win._sync_field_mode()
        offline_policy.set_field_mode(False)


def main() -> int:
    tests = [
        ("core offline session contract", test_core_offline_session_contract),
        ("split FieldModeMixin public HTTP guard", test_split_field_mode_blocks_public_http),
    ]
    for name, fn in tests:
        try:
            fn()
            print(f"OK  {name}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {name}: {exc}")
            return 1
    print("OK: offline session contract (no public HTTP entry points)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
