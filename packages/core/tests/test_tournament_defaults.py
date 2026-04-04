"""Default tournament/team factory tests."""

from __future__ import annotations

from packages.core.src.tournament.defaults import (
    FORMAT_TEAM_COUNTS,
    default_minimal_team,
    default_tournament_config,
)
from packages.shared.src.types.models import TournamentFormat


def test_format_team_counts_covers_all_formats() -> None:
    for fmt in TournamentFormat:
        assert fmt in FORMAT_TEAM_COUNTS
        assert FORMAT_TEAM_COUNTS[fmt] >= 2


def test_default_team_has_three_agents() -> None:
    t = default_minimal_team("alpha")
    assert t.name == "alpha"
    assert len(t.agents) == 3


def test_default_tournament_config_carries_agent_runtime() -> None:
    cfg = default_tournament_config(
        TournamentFormat.DUEL,
        challenge_id="url-shortener-saas",
        budget_limit_usd=50.0,
        agent_runtime="codex_cli",
    )
    assert cfg.format == TournamentFormat.DUEL
    assert len(cfg.teams) == FORMAT_TEAM_COUNTS[TournamentFormat.DUEL]
    assert cfg.agent_runtime == "codex_cli"
    assert cfg.agent_context_window_tokens == 200_000
    assert cfg.agent_context_rollover_ratio == 0.6
