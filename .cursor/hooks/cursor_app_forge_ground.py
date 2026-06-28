"""
App workspaceOpen hook — write Forge ground packet via MindLink OS (no entity activation).

Finds OS root from workspace path or MINDLINK_ROOT; resolves project id from project.mdc contract.
Writes logs/system/forge_ground_latest.md on the OS repo (shared ground packet for App sessions).
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

COOLDOWN_SEC = 120


def _is_mindlink_root(path: Path) -> bool:
    return (path / "mindlink" / "objective.md").is_file()


def find_mindlink_os_root(start: Path) -> Path | None:
    for key in ("MINDLINK_ROOT",):
        val = os.environ.get(key)
        if val:
            candidate = Path(val).resolve()
            if _is_mindlink_root(candidate):
                return candidate
    for path in [start, *start.parents]:
        if _is_mindlink_root(path):
            return path
    return None


def resolve_workspace_root(workspace_roots: list[str] | None) -> Path | None:
    candidates: list[Path] = []
    if workspace_roots:
        candidates.extend(Path(p).resolve() for p in workspace_roots)
    for key in ("CURSOR_PROJECT_DIR",):
        val = os.environ.get(key)
        if val:
            candidates.append(Path(val).resolve())
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        mdc = path / ".cursor" / "rules" / "project.mdc"
        if mdc.is_file() or (path / "SCOPE.md").is_file() or (path / "START.bat").is_file():
            return path
    return candidates[0] if candidates else None


def main() -> int:
    workspace_roots: list[str] | None = None
    try:
        raw = sys.stdin.read()
        if raw.strip():
            data = json.loads(raw)
            workspace_roots = data.get("workspace_roots")
    except json.JSONDecodeError:
        pass

    workspace = resolve_workspace_root(workspace_roots)
    if workspace is None:
        print("{}")
        return 0

    os_root = find_mindlink_os_root(workspace)
    if os_root is None:
        print(json.dumps({"forge_ground": {"action": "skipped", "detail": "mindlink-os root not found"}}))
        return 0

    if str(os_root) not in sys.path:
        sys.path.insert(0, str(os_root))

    stamp = os_root / "logs" / "system" / "forge_ground_latest.json"
    log_path = os_root / "logs" / "system" / "cursor_app_ground.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        line = f"{datetime.now(timezone.utc).isoformat()} {msg}\n"
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    if stamp.is_file() and (time.time() - stamp.stat().st_mtime) < COOLDOWN_SEC:
        log(f"skip cooldown workspace={workspace.name}")
        print(json.dumps({"forge_ground": {"action": "skipped", "detail": "cooldown"}}))
        return 0

    try:
        from mindlink.forge_ground import default_session_goal, resolve_project_id_from_path, write_latest_snapshot

        project_id = resolve_project_id_from_path(workspace)
        goal = default_session_goal(project_id)
        result = write_latest_snapshot(project_id, goal=goal)
        log(
            f"snapshot {project_id} workspace={workspace.name} "
            f"ready={result.get('assessment', {}).get('forge_ready')} "
            f"files={result.get('files_read')}"
        )
        print(
            json.dumps(
                {
                    "forge_ground": {
                        "action": "written",
                        "project_id": project_id,
                        "workspace": str(workspace),
                        **result,
                    }
                }
            )
        )
    except Exception as exc:
        log(f"error workspace={workspace.name}: {exc}")
        print(json.dumps({"forge_ground": {"action": "error", "detail": str(exc)}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
