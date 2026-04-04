"""Default team and tournament configs for CLI and local runs."""

from __future__ import annotations

from packages.shared.src.types.models import (
    AgentConfig,
    AgentRole,
    ModelProvider,
    TeamConfig,
    TournamentConfig,
    TournamentFormat,
)

# Teams required per format (convention; marathon may use milestones with any team count ≥2).
FORMAT_TEAM_COUNTS: dict[TournamentFormat, int] = {
    TournamentFormat.DUEL: 2,
    TournamentFormat.STANDARD: 4,
    TournamentFormat.LEAGUE: 6,
    TournamentFormat.GRAND_PRIX: 8,
    TournamentFormat.MARATHON: 2,
}


def default_minimal_team(name: str) -> TeamConfig:
    """A small default roster (architect, builder, tester) — models route via LiteLLM."""
    return TeamConfig(
        name=name,
        preset="balanced",
        agents=[
            AgentConfig(
                role=AgentRole.ARCHITECT,
                model=ModelProvider.CLAUDE_SONNET_4_6,
                temperature=0.3,
                max_tokens=4096,
                timeout_seconds=60,
                tools=[],
            ),
            AgentConfig(
                role=AgentRole.BUILDER,
                model=ModelProvider.CLAUDE_SONNET_4_6,
                temperature=0.3,
                max_tokens=4096,
                timeout_seconds=60,
                tools=[],
            ),
            AgentConfig(
                role=AgentRole.TESTER,
                model=ModelProvider.CLAUDE_HAIKU_4_5,
                temperature=0.3,
                max_tokens=4096,
                timeout_seconds=60,
                tools=[],
            ),
        ],
    )


def default_teams_for_format(fmt: TournamentFormat) -> list[TeamConfig]:
    n = FORMAT_TEAM_COUNTS[fmt]
    return [default_minimal_team(f"team-{i + 1}") for i in range(n)]


def default_tournament_config(
    fmt: TournamentFormat,
    *,
    challenge_id: str | None,
    budget_limit_usd: float,
    agent_runtime: str,
) -> TournamentConfig:
    return TournamentConfig(
        format=fmt,
        challenge_id=challenge_id,
        teams=default_teams_for_format(fmt),
        budget_limit_usd=budget_limit_usd,
        agent_runtime=agent_runtime,
    )
