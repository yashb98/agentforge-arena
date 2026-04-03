"""Tests for quality runner including module contract gate."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from packages.core.src.tournament.quality_runner import QualityRunner

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_quality_runner_includes_module_contract_check(tmp_path: Path) -> None:
    (tmp_path / "MODULES.json").write_text(
        json.dumps(
            {
                "modules": [
                    {"module_name": "shared", "paths": ["packages/shared/src"], "depends_on": []}
                ]
            }
        ),
        encoding="utf-8",
    )
    sandbox = MagicMock()
    sandbox.run_command = AsyncMock(return_value={"returncode": 0, "stdout": "ok", "stderr": ""})
    runner = QualityRunner(sandbox, repo_root=tmp_path)

    result = await runner.run_for_team(team_id="t1", commands=[])
    assert result.passed
    assert result.command_results[0].name == "module_contracts"


@pytest.mark.asyncio
async def test_quality_runner_fails_on_invalid_module_contracts(tmp_path: Path) -> None:
    (tmp_path / "MODULES.json").write_text(
        json.dumps(
            {
                "modules": [
                    {
                        "module_name": "core",
                        "paths": ["packages/core/src"],
                        "depends_on": ["shared"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    sandbox = MagicMock()
    sandbox.run_command = AsyncMock(return_value={"returncode": 0, "stdout": "ok", "stderr": ""})
    runner = QualityRunner(sandbox, repo_root=tmp_path)

    result = await runner.run_for_team(team_id="t1", commands=[])
    assert not result.passed
    assert result.command_results[0].name == "module_contracts"
