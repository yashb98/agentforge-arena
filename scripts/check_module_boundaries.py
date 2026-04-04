#!/usr/bin/env python3
"""Validate Python imports against MODULES.json (stdlib-only; runs in team sandboxes).

If MODULES.json is missing, exits 0 (nothing to enforce).
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class _Module:
    name: str
    paths: tuple[str, ...]
    public_entrypoints: tuple[str, ...]
    depends_on: tuple[str, ...]


def _load_modules(root: Path) -> dict[str, _Module]:
    path = root / "MODULES.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        items = raw.get("modules", [])
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError("MODULES.json must contain an object or array")

    out: dict[str, _Module] = {}
    for item in items:
        name = str(item["module_name"])
        paths = tuple(str(p) for p in item.get("paths", []))
        if not paths:
            raise ValueError(f"module {name!r} must declare at least one path")
        ep = tuple(str(x) for x in item.get("public_entrypoints", []))
        if not ep:
            raise ValueError(f"module {name!r} must declare public_entrypoints")
        deps = tuple(str(x) for x in item.get("depends_on", []))
        if name in out:
            raise ValueError(f"duplicate module_name {name!r}")
        out[name] = _Module(name=name, paths=paths, public_entrypoints=ep, depends_on=deps)

    for m in out.values():
        for dep in m.depends_on:
            if dep not in out:
                raise ValueError(f"module {m.name!r} depends on unknown module {dep!r}")
    return out


def _file_module(rel_file: Path, modules: dict[str, _Module]) -> str | None:
    """Return module name owning this file path (relative to project root)."""
    parts = rel_file.parts
    best: str | None = None
    best_len = -1
    for m in modules.values():
        for prefix in m.paths:
            p_parts = Path(prefix).parts
            if len(parts) >= len(p_parts) and parts[: len(p_parts)] == p_parts:
                if len(p_parts) > best_len:
                    best_len = len(p_parts)
                    best = m.name
    return best


def _owner_for_import(import_name: str, modules: dict[str, _Module]) -> str | None:
    best_mod: str | None = None
    best_ep_len = -1
    for m in modules.values():
        for ep in m.public_entrypoints:
            if import_name == ep or import_name.startswith(f"{ep}."):
                if len(ep) > best_ep_len:
                    best_ep_len = len(ep)
                    best_mod = m.name
    return best_mod


def _imports_from_file(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            if node.module:
                out.add(node.module)
    return out


def _check(root: Path) -> list[str]:
    modules = _load_modules(root)
    if not modules:
        return []

    allowed_for: dict[str, set[str]] = {}
    for name, m in modules.items():
        allowed_for[name] = {name, *m.depends_on}

    errors: list[str] = []
    for m in modules.values():
        for pref in m.paths:
            base = root / pref
            if not base.is_dir():
                continue
            for py in base.rglob("*.py"):
                rel = py.relative_to(root)
                owner = _file_module(rel, modules)
                if owner is None:
                    continue
                allowed = allowed_for[owner]
                try:
                    ims = _imports_from_file(py)
                except SyntaxError as e:
                    errors.append(f"{rel}: syntax error: {e}")
                    continue
                for imp in ims:
                    target = _owner_for_import(imp, modules)
                    if target is None:
                        continue
                    if target not in allowed:
                        errors.append(
                            f"{rel}: import {imp!r} resolves to module {target!r} "
                            f"not allowed for {owner!r} (allowed: {sorted(allowed)})"
                        )
    return errors


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    if not (root / "MODULES.json").is_file():
        print("check_module_boundaries: no MODULES.json — skipping", file=sys.stderr)
        return 0
    errors = _check(root)
    if errors:
        print("Module boundary violations:", file=sys.stderr)
        for line in errors:
            print(line, file=sys.stderr)
        return 1
    print("check_module_boundaries: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
