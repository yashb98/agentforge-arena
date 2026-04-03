"""TournamentOrchestrator lifecycle tests with DB and I/O mocked."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from packages.core.src.tournament.orchestrator import TournamentOrchestrator
from packages.shared.src.types.models import (
    AgentConfig,
    AgentRole,
    ModelProvider,
    TeamConfig,
    TournamentConfig,
    TournamentFormat,
    TournamentPhase,
)


def _team_cfg(name: str = "a") -> TeamConfig:
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


def _duel_config(**kwargs: object) -> TournamentConfig:
    data = {
        "format": TournamentFormat.DUEL,
        "challenge_id": "url-shortener-saas",
        "teams": [_team_cfg("alpha"), _team_cfg("beta")],
        "budget_limit_usd": 100.0,
    }
    data.update(kwargs)
    return TournamentConfig(**data)


@pytest.fixture()
def mock_session_factory() -> object:
    @asynccontextmanager
    async def _cm() -> object:
        session = MagicMock()
        session.add = MagicMock()
        session.execute = AsyncMock()
        yield session

    return _cm


@pytest.fixture()
def orchestrator(mock_session_factory: object) -> TournamentOrchestrator:
    return TournamentOrchestrator(
        event_bus=MagicMock(publish=AsyncMock(return_value="1-0")),
        sandbox_manager=MagicMock(
            create_sandbox=AsyncMock(return_value="sb1"),
            destroy_sandbox=AsyncMock(),
            write_file=AsyncMock(),
            grant_read_access=AsyncMock(),
        ),
        agent_manager=MagicMock(
            spawn_team=AsyncMock(return_value=[uuid4(), uuid4()]),
            check_team_health=AsyncMock(
                return_value={"all_responsive": True, "unresponsive": []}
            ),
        ),
        judge_service=MagicMock(judge_tournament=AsyncMock(return_value=[])),
    )


@pytest.mark.asyncio
async def test_load_challenge_reads_library(orchestrator: TournamentOrchestrator) -> None:
    body = await orchestrator._load_challenge("url-shortener-saas")
    assert len(body) > 50


@pytest.mark.asyncio
async def test_load_challenge_missing_returns_stub(orchestrator: TournamentOrchestrator) -> None:
    body = await orchestrator._load_challenge("nonexistent-challenge-slug-xyz")
    assert "not found" in body.lower()


def test_calculate_rounds(orchestrator: TournamentOrchestrator) -> None:
    assert orchestrator._calculate_rounds(TournamentFormat.DUEL, 2) == 1
    assert orchestrator._calculate_rounds(TournamentFormat.STANDARD, 8) == 3
    assert orchestrator._calculate_rounds(TournamentFormat.LEAGUE, 5) == 4
    assert orchestrator._calculate_rounds(TournamentFormat.GRAND_PRIX, 8) >= 3


@pytest.mark.asyncio
async def test_create_tournament_budget_exceeds_max_raises(
    orchestrator: TournamentOrchestrator,
) -> None:
    settings = MagicMock()
    settings.llm.budget_per_tournament_usd = 50.0
    cfg = _duel_config(budget_limit_usd=999.0)
    with (
        patch(
            "packages.core.src.tournament.orchestrator.get_settings",
            return_value=settings,
        ),
        pytest.raises(ValueError, match="Budget"),
    ):
        await orchestrator.create_tournament(cfg)


@pytest.mark.asyncio
async def test_create_tournament_persists_and_publishes(
    orchestrator: TournamentOrchestrator,
    mock_session_factory: object,
) -> None:
    settings = MagicMock()
    settings.llm.budget_per_tournament_usd = 500.0
    cfg = _duel_config()
    with (
        patch(
            "packages.core.src.tournament.orchestrator.get_settings",
            return_value=settings,
        ),
        patch(
            "packages.core.src.tournament.orchestrator.get_session",
            mock_session_factory,
        ),
    ):
        t = await orchestrator.create_tournament(cfg)
    assert t.challenge_id == "url-shortener-saas"
    assert t.id in orchestrator._active_tournaments
    orchestrator._events.publish.assert_awaited()


@pytest.mark.asyncio
async def test_start_tournament_provisions_teams(
    orchestrator: TournamentOrchestrator,
    mock_session_factory: object,
) -> None:
    settings = MagicMock()
    settings.llm.budget_per_tournament_usd = 500.0
    cfg = _duel_config()
    with (
        patch(
            "packages.core.src.tournament.orchestrator.get_settings",
            return_value=settings,
        ),
        patch(
            "packages.core.src.tournament.orchestrator.get_session",
            mock_session_factory,
        ),
    ):
        t = await orchestrator.create_tournament(cfg)

    async def _noop_health(_t: object) -> None:
        return None

    with (
        patch(
            "packages.core.src.tournament.orchestrator.get_session",
            mock_session_factory,
        ),
        patch.object(orchestrator, "_deliver_challenge", new_callable=AsyncMock),
        patch.object(orchestrator, "_transition_phase", new_callable=AsyncMock),
        patch.object(orchestrator, "_health_monitor", _noop_health),
    ):
        out = await orchestrator.start_tournament(t.id)

    assert len(out.team_ids) == 2
    orchestrator._sandbox.create_sandbox.assert_awaited()
    orchestrator._agents.spawn_team.assert_awaited()
    assert t.id in orchestrator._health_tasks


@pytest.mark.asyncio
async def test_start_tournament_not_found(
    orchestrator: TournamentOrchestrator,
) -> None:
    with pytest.raises(ValueError, match="not found"):
        await orchestrator.start_tournament(uuid4())


@pytest.mark.asyncio
async def test_start_tournament_wrong_phase(
    orchestrator: TournamentOrchestrator,
    mock_session_factory: object,
) -> None:
    settings = MagicMock()
    settings.llm.budget_per_tournament_usd = 500.0
    with (
        patch(
            "packages.core.src.tournament.orchestrator.get_settings",
            return_value=settings,
        ),
        patch(
            "packages.core.src.tournament.orchestrator.get_session",
            mock_session_factory,
        ),
    ):
        t = await orchestrator.create_tournament(_duel_config())
    t.current_phase = TournamentPhase.BUILD
    with pytest.raises(ValueError, match="expected PREP"):
        await orchestrator.start_tournament(t.id)


@pytest.mark.asyncio
async def test_cancel_tournament_not_found(
    orchestrator: TournamentOrchestrator,
) -> None:
    with pytest.raises(ValueError, match="not found"):
        await orchestrator.cancel_tournament(uuid4())


@pytest.mark.asyncio
async def test_cancel_tournament_cleans_up(
    orchestrator: TournamentOrchestrator,
    mock_session_factory: object,
) -> None:
    settings = MagicMock()
    settings.llm.budget_per_tournament_usd = 500.0
    with (
        patch(
            "packages.core.src.tournament.orchestrator.get_settings",
            return_value=settings,
        ),
        patch(
            "packages.core.src.tournament.orchestrator.get_session",
            mock_session_factory,
        ),
    ):
        t = await orchestrator.create_tournament(_duel_config())
    t.team_ids.extend([uuid4(), uuid4()])

    with patch(
        "packages.core.src.tournament.orchestrator.get_session",
        mock_session_factory,
    ):
        done = await orchestrator.cancel_tournament(t.id)

    assert done.current_phase == TournamentPhase.CANCELLED
    orchestrator._sandbox.destroy_sandbox.assert_awaited()
