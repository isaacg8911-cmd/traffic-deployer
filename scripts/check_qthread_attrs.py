"""AST guard: QThread subclasses must not assign reserved Qt method names.

Enforces OS rule `.cursor/rules/framework-shadow.mdc` (universal) /
fingerprint FP-QTHREAD-SHADOW.

Proven: Traffic Deployer — `self.start = gps` overwrote QThread.start() →
TypeError: 'NoneType' object is not callable when BUILD ROUTE ran.

Usage:
  python scripts/check_qthread_attrs.py [path ...]
"""
from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Methods that must stay callable on QThread instances (field crash class).
RESERVED = frozenset({
    "start", "run", "quit", "wait", "exec", "exec_", "terminate",
    "exit", "finished", "started", "isRunning", "requestInterruption",
    "msleep", "sleep", "usleep", "setPriority", "setStackSize",
    "moveToThread", "deleteLater", "blockSignals",
})


def _bases_include_qthread(bases: list[ast.expr]) -> bool:
    for b in bases:
        if isinstance(b, ast.Name) and b.id == "QThread":
            return True
        if isinstance(b, ast.Attribute) and b.attr == "QThread":
            return True
    return False


def scan_file(path: str) -> list[str]:
    try:
        src = open(path, encoding="utf-8").read()
    except OSError as exc:
        return [f"{path}: read error: {exc}"]
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError as exc:
        return [f"{path}: syntax error: {exc}"]

    hits: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            if not _bases_include_qthread(node.bases):
                self.generic_visit(node)
                return
            def _check_self_attr(attr: str, lineno: int) -> None:
                if attr in RESERVED:
                    hits.append(
                        f"{path}:{lineno}: "
                        f"QThread subclass {node.name} assigns self.{attr} "
                        f"(shadows QThread.{attr} — FP-QTHREAD-SHADOW)"
                    )

            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    for target in child.targets:
                        if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                        ):
                            _check_self_attr(target.attr, child.lineno)
                elif isinstance(child, ast.AnnAssign):
                    t = child.target
                    if (
                        isinstance(t, ast.Attribute)
                        and isinstance(t.value, ast.Name)
                        and t.value.id == "self"
                    ):
                        _check_self_attr(t.attr, child.lineno)
                elif isinstance(child, ast.Call):
                    # setattr(self, "start", ...)
                    fn = child.func
                    if isinstance(fn, ast.Name) and fn.id == "setattr" and len(child.args) >= 2:
                        obj, name = child.args[0], child.args[1]
                        if (
                            isinstance(obj, ast.Name)
                            and obj.id == "self"
                            and isinstance(name, ast.Constant)
                            and isinstance(name.value, str)
                        ):
                            _check_self_attr(name.value, child.lineno)
            self.generic_visit(node)

    Visitor().visit(tree)
    return hits


def iter_py_files(paths: list[str]) -> list[str]:
    out: list[str] = []
    for p in paths:
        if os.path.isfile(p) and p.endswith(".py"):
            out.append(p)
        elif os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                if any(skip in root for skip in (".venv", "__pycache__", "build", "dist")):
                    continue
                for name in files:
                    if name.endswith(".py"):
                        out.append(os.path.join(root, name))
    return sorted(set(out))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    targets = args or [os.path.join(ROOT, "ui"), os.path.join(ROOT, "core")]
    files = iter_py_files(targets)
    all_hits: list[str] = []
    for f in files:
        all_hits.extend(scan_file(f))
    if all_hits:
        print("FAIL FP-QTHREAD-SHADOW:")
        for h in all_hits:
            print(f"  {h}")
        return 1
    print(f"OK QThread attr scan — {len(files)} files, no reserved shadows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
