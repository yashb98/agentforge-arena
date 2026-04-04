"""CLI entry: create/start tournaments without the HTTP server (e.g. Cursor terminal).

Uses the same wiring as ``packages.api.src.main`` lifespan. Model routing stays
multi-vendor via LiteLLM; ``agent_runtime`` selects which *coding agent* stack
spawns in sandboxes (native vs Claude Code vs Codex, etc.) — runners read it from config/events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any
from uuid import UUID

import click

from packages.core.src.tournament.bootstrap import tournament_runtime_stack
from packages.core.src.tournament.defaults import default_tournament_config
from packages.shared.src.types.models import TournamentFormat, TournamentPhase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """AgentForge Arena — tournament commands (headless, same stack as the API)."""


@cli.command("start")
@click.option(
    "--format",
    "fmt",
    type=click.Choice([f.value for f in TournamentFormat], case_sensitive=False),
    default="duel",
    show_default=True,
    help="Tournament bracket size",
)
@click.option(
    "--challenge-id",
    default=None,
    help="Challenge library id; random pick if omitted",
)
@click.option(
    "--budget",
    type=float,
    default=100.0,
    show_default=True,
    help="LLM budget cap (USD) for this tournament",
)
@click.option(
    "--agent-runtime",
    default="arena_native",
    show_default=True,
    help=(
        "Coding-agent backend: arena_native (default in-process), claude_code, "
        "codex_cli, gemini_cli, opencode, … Spawners should read tournament.config.agent_runtime."
    ),
)
@click.option(
    "--wait/--no-wait",
    default=False,
    help="Block until the tournament reaches a terminal phase (local dev)",
)
def start_cmd(
    fmt: str,
    challenge_id: str | None,
    budget: float,
    agent_runtime: str,
    wait: bool,
) -> None:
    """Create a tournament, start it (sandboxes + agents + RESEARCH phase), print JSON summary."""
    fmt_enum = TournamentFormat(fmt.lower())
    asyncio.run(
        _start_async(
            fmt=fmt_enum,
            challenge_id=challenge_id,
            budget_limit_usd=budget,
            agent_runtime=agent_runtime,
            wait=wait,
        )
    )


async def _wait_terminal(orchestrator: object, tournament_id: UUID) -> None:
    while True:
        active: dict[UUID, Any] = getattr(orchestrator, "_active_tournaments", {})
        t = active.get(tournament_id)
        if t is None:
            return
        if t.current_phase in (TournamentPhase.COMPLETE, TournamentPhase.CANCELLED):
            return
        await asyncio.sleep(2.0)


async def _start_async(
    *,
    fmt: TournamentFormat,
    challenge_id: str | None,
    budget_limit_usd: float,
    agent_runtime: str,
    wait: bool,
) -> None:
    config = default_tournament_config(
        fmt,
        challenge_id=challenge_id,
        budget_limit_usd=budget_limit_usd,
        agent_runtime=agent_runtime,
    )
    async with tournament_runtime_stack() as stack:
        orch = stack.orchestrator
        tournament = await orch.create_tournament(config)
        tid = tournament.id
        started = await orch.start_tournament(tid)
        out = {
            "tournament_id": str(started.id),
            "challenge_id": started.challenge_id,
            "format": started.format.value,
            "phase": started.current_phase.value,
            "agent_runtime": started.config.agent_runtime,
            "team_ids": [str(x) for x in started.team_ids],
        }
        click.echo(json.dumps(out, indent=2))
        if wait:
            logger.info("Waiting until tournament %s is terminal…", tid)
            await _wait_terminal(orch, tid)
            active = getattr(orch, "_active_tournaments", {})
            final = active.get(tid)
            if final:
                click.echo(
                    json.dumps(
                        {
                            "tournament_id": str(final.id),
                            "phase": final.current_phase.value,
                            "winner_team_id": str(final.winner_team_id)
                            if final.winner_team_id
                            else None,
                        },
                        indent=2,
                    )
                )


def main() -> None:
    try:
        cli(standalone_mode=True)
    except click.ClickException as e:
        e.show()
        sys.exit(e.exit_code)


if __name__ == "__main__":
    main()
