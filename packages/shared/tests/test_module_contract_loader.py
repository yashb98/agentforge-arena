"""Tests for MODULES.json loader and dependency validation."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from packages.shared.src.module_contract_loader import load_module_contracts

if TYPE_CHECKING:
    from pathlib import Path


def test_load_module_contracts_valid(tmp_path: Path) -> None:
    payload = {
        "modules": [
            {
                "module_name": "shared",
                "paths": ["packages/shared/src"],
                "depends_on": [],
            },
            {
                "module_name": "core",
                "paths": ["packages/core/src"],
                "depends_on": ["shared"],
            },
        ]
    }
    (tmp_path / "MODULES.json").write_text(json.dumps(payload), encoding="utf-8")
    out = load_module_contracts(tmp_path)
    assert set(out.keys()) == {"shared", "core"}


def test_load_module_contracts_unknown_dependency_raises(tmp_path: Path) -> None:
    payload = {
        "modules": [
            {
                "module_name": "core",
                "paths": ["packages/core/src"],
                "depends_on": ["missing"],
            }
        ]
    }
    (tmp_path / "MODULES.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown module"):
        load_module_contracts(tmp_path)
