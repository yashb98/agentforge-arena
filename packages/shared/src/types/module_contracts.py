"""
Module boundary contracts for large multi-package agent builds (50k+ LOC).

Teams declare manifests (JSON / Pydantic) so parallel work stays mergeable.
"""

from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field


class ModuleManifestDict(TypedDict, total=False):
    """Minimal fields for a module boundary declaration (e.g. in repo root MODULES.json)."""

    module_name: str
    public_entrypoints: list[str]
    depends_on: list[str]
    owners: list[str]
    paths: list[str]


class ModuleManifest(BaseModel):
    """Validated module contract entry."""

    model_config = ConfigDict(extra="forbid")

    module_name: str = Field(min_length=1)
    paths: list[str] = Field(min_length=1)
    public_entrypoints: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    owners: list[str] = Field(default_factory=list)
