"""TournamentOrchestrator lifecycle tests with DB and I/O mocked."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from packages.core.src.tournament.orchestrator import TournamentOrchestrator
from packages.shared.src.types.models import (
    AgentConfig,
    AgentRole,
    ModelProvider,
    TeamConfig,
    Tournament,
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
    assert orchestrator._calculate_rounds(TournamentFormat.MARATHON, 4) == 1


@pytest.mark.asyncio
async def test_advance_marathon_calls_transition(
    orchestrator: TournamentOrchestrator,
    mock_session_factory: object,
) -> None:
    settings = MagicMock()
    settings.llm.budget_per_tournament_usd = 500.0
    cfg = _duel_config().model_copy(update={"format": TournamentFormat.MARATHON})
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
    with patch.object(orchestrator, "_transition_phase", new_callable=AsyncMock) as tp:
        await orchestrator.advance_milestone(t.id)
    tp.assert_awaited_once()


@pytest.mark.asyncio
async def test_advance_milestone_rejects_non_marathon(
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
    with pytest.raises(ValueError, match="marathon"):
        await orchestrator.advance_milestone(t.id)


@pytest.mark.asyncio
async def test_checkpoint_tournament_publishes_event(
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
        out = await orchestrator.checkpoint_tournament(t.id)
    assert out.id == t.id
    orchestrator._events.publish.assert_awaited()


@pytest.mark.asyncio
async def test_restore_durable_empty(orchestrator: TournamentOrchestrator) -> None:
    exec_result = MagicMock()
    exec_result.scalars.return_value.unique.return_value.all.return_value = []

    @asynccontextmanager
    async def cm() -> object:
        session = MagicMock()
        session.execute = AsyncMock(return_value=exec_result)
        yield session

    with patch("packages.core.src.tournament.orchestrator.get_session", cm):
        await orchestrator.restore_durable_tournaments()
    assert orchestrator._active_tournaments == {}


@pytest.mark.asyncio
async def test_restore_durable_rehydrates_prep_tournament(
    orchestrator: TournamentOrchestrator,
) -> None:
    tid = uuid4()
    trow = MagicMock()
    trow.id = tid
    trow.format = "duel"
    trow.current_phase = "prep"
    trow.challenge_id = "url-shortener-saas"
    trow.config = _duel_config().model_dump(mode="json")
    trow.current_round = 1
    trow.total_rounds = 1
    trow.started_at = None
    trow.completed_at = None
    trow.winner_team_id = None
    trow.total_cost_usd = 0.0
    trow.runtime_state = {}
    trow.teams = []

    exec_result = MagicMock()
    exec_result.scalars.return_value.unique.return_value.all.return_value = [trow]

    @asynccontextmanager
    async def cm() -> object:
        session = MagicMock()
        session.execute = AsyncMock(return_value=exec_result)
        yield session

    with patch("packages.core.src.tournament.orchestrator.get_session", cm):
        await orchestrator.restore_durable_tournaments()
    assert tid in orchestrator._active_tournaments
    assert orchestrator._active_tournaments[tid].current_phase == TournamentPhase.PREP


@pytest.mark.asyncio
async def test_restore_skips_stale_timer_phase(
    orchestrator: TournamentOrchestrator,
) -> None:
    tid = uuid4()
    trow = MagicMock()
    trow.id = tid
    trow.format = "duel"
    trow.current_phase = "research"
    trow.challenge_id = "url-shortener-saas"
    trow.config = _duel_config().model_dump(mode="json")
    trow.current_round = 1
    trow.total_rounds = 1
    trow.started_at = datetime.utcnow()
    trow.completed_at = None
    trow.winner_team_id = None
    trow.total_cost_usd = 0.0
    trow.runtime_state = {
        "deadline_utc": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        "phase_timer_phase": "build",
        "duration_seconds": 3600,
    }
    trow.teams = []

    exec_result = MagicMock()
    exec_result.scalars.return_value.unique.return_value.all.return_value = [trow]

    @asynccontextmanager
    async def cm() -> object:
        session = MagicMock()
        session.execute = AsyncMock(return_value=exec_result)
        yield session

    with patch("packages.core.src.tournament.orchestrator.get_session", cm):
        await orchestrator.restore_durable_tournaments()
    assert tid in orchestrator._active_tournaments
    assert tid not in orchestrator._phase_timers


@pytest.mark.asyncio
async def test_hydrate_tournament_from_db(
    orchestrator: TournamentOrchestrator,
) -> None:
    tid = uuid4()
    trow = MagicMock()
    trow.id = tid
    trow.format = "duel"
    trow.current_phase = "prep"
    trow.challenge_id = "url-shortener-saas"
    trow.config = _duel_config().model_dump(mode="json")
    trow.current_round = 1
    trow.total_rounds = 1
    trow.started_at = None
    trow.completed_at = None
    trow.winner_team_id = None
    trow.total_cost_usd = 0.0
    trow.teams = []

    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = trow

    @asynccontextmanager
    async def cm() -> object:
        session = MagicMock()
        session.execute = AsyncMock(return_value=exec_result)
        yield session

    with patch("packages.core.src.tournament.orchestrator.get_session", cm):
        out = await orchestrator.hydrate_tournament_from_db(tid)
    assert out.id == tid
    assert tid in orchestrator._active_tournaments


@pytest.mark.asyncio
async def test_hydrate_missing_row_raises(orchestrator: TournamentOrchestrator) -> None:
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = None

    @asynccontextmanager
    async def cm() -> object:
        session = MagicMock()
        session.execute = AsyncMock(return_value=exec_result)
        yield session

    tid = uuid4()
    with patch("packages.core.src.tournament.orchestrator.get_session", cm):
        with pytest.raises(ValueError, match="not found in database"):
            await orchestrator.hydrate_tournament_from_db(tid)


@pytest.mark.asyncio
async def test_restore_marathon_skips_auto_timer(
    orchestrator: TournamentOrchestrator,
) -> None:
    tid = uuid4()
    trow = MagicMock()
    trow.id = tid
    trow.format = "marathon"
    trow.current_phase = "research"
    trow.challenge_id = "url-shortener-saas"
    cfg = _duel_config().model_copy(update={"format": TournamentFormat.MARATHON})
    trow.config = cfg.model_dump(mode="json")
    trow.current_round = 1
    trow.total_rounds = 1
    trow.started_at = None
    trow.completed_at = None
    trow.winner_team_id = None
    trow.total_cost_usd = 0.0
    trow.runtime_state = {"milestone_mode": True}
    trow.teams = []

    exec_result = MagicMock()
    exec_result.scalars.return_value.unique.return_value.all.return_value = [trow]

    @asynccontextmanager
    async def cm() -> object:
        session = MagicMock()
        session.execute = AsyncMock(return_value=exec_result)
        yield session

    with patch("packages.core.src.tournament.orchestrator.get_session", cm):
        await orchestrator.restore_durable_tournaments()
    assert tid in orchestrator._active_tournaments
    assert tid not in orchestrator._phase_timers


@pytest.mark.asyncio
async def test_restore_schedules_timer_from_runtime_deadline(
    orchestrator: TournamentOrchestrator,
) -> None:
    tid = uuid4()
    team_id = uuid4()
    team_m = MagicMock()
    team_m.id = team_id
    future_deadline = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    trow = MagicMock()
    trow.id = tid
    trow.format = "duel"
    trow.current_phase = "research"
    trow.challenge_id = "url-shortener-saas"
    trow.config = _duel_config().model_dump(mode="json")
    trow.current_round = 1
    trow.total_rounds = 1
    trow.started_at = datetime.utcnow()
    trow.completed_at = None
    trow.winner_team_id = None
    trow.total_cost_usd = 0.0
    trow.runtime_state = {
        "deadline_utc": future_deadline,
        "phase_timer_phase": "research",
        "duration_seconds": 3600,
        "team_ids": [str(team_id)],
    }
    trow.teams = [team_m]

    exec_result = MagicMock()
    exec_result.scalars.return_value.unique.return_value.all.return_value = [trow]

    @asynccontextmanager
    async def cm() -> object:
        session = MagicMock()
        session.execute = AsyncMock(return_value=exec_result)
        yield session

    with patch("packages.core.src.tournament.orchestrator.get_session", cm):
        await orchestrator.restore_durable_tournaments()
    assert tid in orchestrator._phase_timers
    orchestrator._phase_timers[tid].cancel()


@pytest.mark.asyncio
async def test_phase_timer_zero_remaining_triggers_transition(
    orchestrator: TournamentOrchestrator,
) -> None:
    cfg = _duel_config()
    tournament = Tournament(
        id=uuid4(),
        format=TournamentFormat.DUEL,
        challenge_id="url-shortener-saas",
        config=cfg,
        team_ids=[],
        current_phase=TournamentPhase.RESEARCH,
    )
    with patch.object(orchestrator, "_transition_phase", new_callable=AsyncMock) as tp:
        await orchestrator._phase_timer(
            tournament,
            TournamentPhase.RESEARCH,
            3600,
            resume_remaining_seconds=0,
        )
    tp.assert_awaited_once()


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
