"""Tournament / team / agent cost rollups."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from packages.shared.src.llm.cost_aggregate import summarize_tournament_costs


def test_summarize_tournament_costs_splits_teams_and_agents() -> None:
    tid = uuid4()
    t1, t2 = uuid4(), uuid4()
    a1, a2 = uuid4(), uuid4()
    teams = [
        SimpleNamespace(id=t1, total_cost_usd=1.5),
        SimpleNamespace(id=t2, total_cost_usd=2.0),
    ]
    agents = [
        SimpleNamespace(id=a1, team_id=t1, total_cost_usd=0.5, total_tokens_used=100),
        SimpleNamespace(id=a2, team_id=t2, total_cost_usd=1.25, total_tokens_used=200),
    ]
    s = summarize_tournament_costs(tournament_id=tid, teams=teams, agents=agents)
    assert s.tournament_total_usd == 3.5
    assert s.team_totals_usd[str(t1)] == 1.5
    assert s.agent_totals_usd[str(a2)] == 1.25
    assert s.agent_tokens[str(a1)] == 100
    assert s.team_count == 2
    assert s.agent_count == 2
