"""Load and validate repository module contracts."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from packages.shared.src.types.module_contracts import ModuleManifest

if TYPE_CHECKING:
    from pathlib import Path


def load_module_contracts(repo_root: Path) -> dict[str, ModuleManifest]:
    """Load MODULES.json and validate dependency references."""
    path = repo_root / "MODULES.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        modules_raw = raw.get("modules", [])
    elif isinstance(raw, list):
        modules_raw = raw
    else:
        raise ValueError("MODULES.json must be an object or array")

    manifests = [ModuleManifest.model_validate(item) for item in modules_raw]
    by_name = {m.module_name: m for m in manifests}
    if len(by_name) != len(manifests):
        raise ValueError("Duplicate module_name in MODULES.json")
    for manifest in manifests:
        for dep in manifest.depends_on:
            if dep not in by_name:
                raise ValueError(
                    f"Module {manifest.module_name!r} depends on unknown module {dep!r}"
                )
    return by_name
