"""
Module boundary contracts for large multi-package agent builds (50k+ LOC).

Teams declare manifests (JSON / Pydantic) so parallel work stays mergeable.
"""

from __future__ import annotations

from typing import TypedDict


class ModuleManifestDict(TypedDict, total=False):
    """Minimal fields for a module boundary declaration (e.g. in repo root MODULES.json)."""

    module_name: str
    public_entrypoints: list[str]
    depends_on: list[str]
