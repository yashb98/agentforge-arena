"""Continuous quality runner for challenge-defined command gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from packages.shared.src.module_contract_loader import load_module_contracts

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from packages.shared.src.types.challenge_spec import QualityCommandSpec


@dataclass(slots=True)
class QualityCommandResult:
    """Execution outcome for one quality command."""

    name: str
    cmd: list[str]
    required: bool
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


@dataclass(slots=True)
class QualityRunResult:
    """Aggregate quality pipeline result for one team."""

    team_id: str
    command_results: list[QualityCommandResult]

    @property
    def passed(self) -> bool:
        return all((not r.required) or r.passed for r in self.command_results)


class QualityRunner:
    """Execute challenge quality commands against a team sandbox."""

    def __init__(self, sandbox_manager: object, *, repo_root: Path | None = None) -> None:
        self._sandbox = sandbox_manager
        self._repo_root = repo_root

    async def run_for_team(
        self,
        *,
        team_id: str,
        commands: Sequence[QualityCommandSpec],
    ) -> QualityRunResult:
        results: list[QualityCommandResult] = []
        if self._repo_root is not None:
            try:
                load_module_contracts(self._repo_root)
                results.append(
                    QualityCommandResult(
                        name="module_contracts",
                        cmd=["validate", "MODULES.json"],
                        required=True,
                        returncode=0,
                        stdout="module contracts valid",
                        stderr="",
                    )
                )
            except Exception as exc:
                results.append(
                    QualityCommandResult(
                        name="module_contracts",
                        cmd=["validate", "MODULES.json"],
                        required=True,
                        returncode=1,
                        stdout="",
                        stderr=str(exc),
                    )
                )
        for command in commands:
            outcome = await self._sandbox.run_command(team_id, command.cmd)  # type: ignore[attr-defined]
            results.append(
                QualityCommandResult(
                    name=command.name,
                    cmd=list(command.cmd),
                    required=command.required,
                    returncode=int(outcome.get("returncode", 1)),
                    stdout=str(outcome.get("stdout", "")),
                    stderr=str(outcome.get("stderr", "")),
                )
            )
        return QualityRunResult(team_id=team_id, command_results=results)
