"""Roll up LLM spend for tournaments, teams, and agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID


class HasAgentCost(Protocol):
    id: UUID
    team_id: UUID
    total_cost_usd: float
    total_tokens_used: int


class HasTeamCost(Protocol):
    id: UUID
    total_cost_usd: float


@dataclass(slots=True)
class TournamentCostSummary:
    """Aggregated API cost view for dashboards and budget checks."""

    tournament_id: UUID
    tournament_total_usd: float
    team_totals_usd: dict[str, float] = field(default_factory=dict)
    agent_totals_usd: dict[str, float] = field(default_factory=dict)
    agent_tokens: dict[str, int] = field(default_factory=dict)

    @property
    def team_count(self) -> int:
        return len(self.team_totals_usd)

    @property
    def agent_count(self) -> int:
        return len(self.agent_totals_usd)


def summarize_tournament_costs(
    *,
    tournament_id: UUID,
    teams: list[HasTeamCost],
    agents: list[HasAgentCost],
) -> TournamentCostSummary:
    """
    Build a summary from in-memory or ORM rows exposing ``total_cost_usd``.

    Team rows should reflect persisted aggregates; agent rows refine the split.
    """
    team_totals = {str(t.id): float(t.total_cost_usd) for t in teams}
    agent_totals: dict[str, float] = {}
    agent_tokens: dict[str, int] = {}
    for a in agents:
        aid = str(a.id)
        agent_totals[aid] = float(a.total_cost_usd)
        agent_tokens[aid] = int(a.total_tokens_used)

    tournament_total = sum(team_totals.values(), 0.0)
    if not team_totals and agent_totals:
        tournament_total = sum(agent_totals.values(), 0.0)

    return TournamentCostSummary(
        tournament_id=tournament_id,
        tournament_total_usd=tournament_total,
        team_totals_usd=team_totals,
        agent_totals_usd=agent_totals,
        agent_tokens=agent_tokens,
    )
