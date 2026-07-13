"""Prove Wi-Fi update staging overwrites one slot (no version pile-up)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import auto_updater as au


def _touch(path: str, text: str = "x") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main() -> int:
    fails: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        data = os.path.join(tmp, "tds_data")
        os.makedirs(data)

        # Simulate leftover versioned staging from older builds + a fresh slot.
        stale_a = os.path.join(data, au.STAGING_DIRNAME, "extracted-1.0.11", "junk.bin")
        stale_b = os.path.join(data, au.STAGING_DIRNAME, "TrafficDeployer-1.0.11.zip")
        _touch(stale_a, "old")
        _touch(stale_b, "oldzip")

        au._clear_staging(data)
        staging = os.path.join(data, au.STAGING_DIRNAME)
        if os.path.isdir(staging):
            fails.append("staging should be gone after _clear_staging")

        # Fixed names only
        if au.STAGING_ZIP_NAME != "update.zip":
            fails.append(f"expected update.zip, got {au.STAGING_ZIP_NAME}")
        if au.STAGING_EXTRACT_NAME != "extracted":
            fails.append(f"expected extracted, got {au.STAGING_EXTRACT_NAME}")

        # stage_bundle_for_apply copies then clears staging
        bundle = os.path.join(tmp, "bundle")
        os.makedirs(os.path.join(bundle, "_internal", "web"), exist_ok=True)
        os.makedirs(os.path.join(bundle, "web"), exist_ok=True)
        _touch(os.path.join(bundle, "TrafficDeployer.exe"), "exe")
        _touch(os.path.join(bundle, "_internal", "web", "index.html"), "map")
        _touch(os.path.join(bundle, "web", "index.html"), "map")
        # Put a fake download under staging that must vanish after stage
        _touch(os.path.join(data, au.STAGING_DIRNAME, au.STAGING_ZIP_NAME), "zip")
        _touch(
            os.path.join(data, au.STAGING_DIRNAME, au.STAGING_EXTRACT_NAME, "x.txt"),
            "extract",
        )

        ready = au.stage_bundle_for_apply(bundle, data)
        if not os.path.isfile(os.path.join(ready, "TrafficDeployer.exe")):
            fails.append("update_ready missing exe")
        if os.path.isdir(staging):
            fails.append("staging must be cleared after stage_bundle_for_apply")

        # Successful apply cleanup removes ready + staging leftovers
        _touch(os.path.join(data, ".update_applied"), "1.0.99")
        leftover = os.path.join(data, au.STAGING_DIRNAME, "leftover.bin")
        _touch(leftover, "z")
        au._clear_pending_if_current("1.0.99", data)
        if os.path.isdir(os.path.join(data, au.READY_DIRNAME)):
            fails.append("update_ready should clear after applied")
        if os.path.isdir(staging):
            fails.append("staging should clear after applied")

    if fails:
        for f in fails:
            print(f"FAIL: {f}")
        return 1
    print("PASS: update overwrite slot (staging fixed names + cleanup)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
