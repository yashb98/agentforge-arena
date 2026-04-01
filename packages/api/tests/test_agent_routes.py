"""
AgentForge Arena — Tests for Agent Routes

Covers:
  GET /api/v1/tournaments/{tournament_id}/agents
  GET /api/v1/tournaments/{tournament_id}/teams/{team_id}/agents
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from packages.shared.src.types.models import (
    Agent,
    AgentRole,
    AgentStatus,
    ModelProvider,
)


# ---------------------------------------------------------------------------
# Helpers / Factories
# ---------------------------------------------------------------------------


def make_agent(
    *,
    team_id: UUID,
    tournament_id: UUID,
    role: AgentRole = AgentRole.BUILDER,
    status: AgentStatus = AgentStatus.ACTIVE,
) -> Agent:
    """Create a minimal Agent domain object for testing."""
    return Agent(
        id=uuid4(),
        team_id=team_id,
        tournament_id=tournament_id,
        role=role,
        model=ModelProvider.CLAUDE_SONNET_4_6,
        status=status,
        total_tokens_used=100,
        total_cost_usd=0.01,
        actions_count=5,
        errors_count=0,
        last_heartbeat=datetime(2026, 3, 31, 12, 0, 0),
    )


def make_tournament_stub(team_ids: list[UUID]) -> MagicMock:
    """Create a stub tournament object with a team_ids attribute."""
    t = MagicMock()
    t.team_ids = team_ids
    return t


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tournament_id() -> UUID:
    return uuid4()


@pytest.fixture()
def team_id_a() -> UUID:
    return uuid4()


@pytest.fixture()
def team_id_b() -> UUID:
    return uuid4()


@pytest.fixture()
def mock_orchestrator(tournament_id: UUID, team_id_a: UUID, team_id_b: UUID) -> MagicMock:
    """Orchestrator whose _active_tournaments contains one tournament."""
    orch = MagicMock()
    orch._active_tournaments = {
        tournament_id: make_tournament_stub([team_id_a, team_id_b]),
    }
    return orch


@pytest.fixture()
def mock_agent_manager(tournament_id: UUID, team_id_a: UUID, team_id_b: UUID) -> MagicMock:
    """Agent manager that returns one agent per team."""
    mgr = MagicMock()

    async def _get_team_agents(team_id: UUID) -> list[Agent]:
        return [make_agent(team_id=team_id, tournament_id=tournament_id)]

    mgr.get_team_agents = _get_team_agents
    return mgr


# ---------------------------------------------------------------------------
# list_tournament_agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tournament_agents_returns_all_agents(
    tournament_id: UUID,
    team_id_a: UUID,
    team_id_b: UUID,
    mock_orchestrator: MagicMock,
    mock_agent_manager: MagicMock,
) -> None:
    """Should return one AgentResponse per team (two teams → two agents)."""
    from packages.api.src.routes.agents import list_tournament_agents

    result = await list_tournament_agents(
        tournament_id=tournament_id,
        orchestrator=mock_orchestrator,
        agent_manager=mock_agent_manager,
    )

    assert len(result) == 2
    team_ids_returned = {r.team_id for r in result}
    assert team_id_a in team_ids_returned
    assert team_id_b in team_ids_returned


@pytest.mark.asyncio
async def test_list_tournament_agents_response_fields(
    tournament_id: UUID,
    mock_orchestrator: MagicMock,
    mock_agent_manager: MagicMock,
) -> None:
    """Each returned item should have all required AgentResponse fields."""
    from packages.api.src.routes.agents import list_tournament_agents

    result = await list_tournament_agents(
        tournament_id=tournament_id,
        orchestrator=mock_orchestrator,
        agent_manager=mock_agent_manager,
    )

    agent = result[0]
    assert isinstance(agent.id, UUID)
    assert isinstance(agent.team_id, UUID)
    assert agent.role == AgentRole.BUILDER
    assert agent.model == ModelProvider.CLAUDE_SONNET_4_6
    assert agent.status == AgentStatus.ACTIVE
    assert agent.total_tokens_used == 100
    assert agent.total_cost_usd == pytest.approx(0.01)
    assert agent.actions_count == 5
    assert agent.errors_count == 0
    assert agent.last_heartbeat is not None


@pytest.mark.asyncio
async def test_list_tournament_agents_unknown_tournament_raises_404(
    mock_orchestrator: MagicMock,
    mock_agent_manager: MagicMock,
) -> None:
    """Should raise HTTP 404 when the tournament ID is not active."""
    from fastapi import HTTPException

    from packages.api.src.routes.agents import list_tournament_agents

    unknown_id = uuid4()
    with pytest.raises(HTTPException) as exc_info:
        await list_tournament_agents(
            tournament_id=unknown_id,
            orchestrator=mock_orchestrator,
            agent_manager=mock_agent_manager,
        )

    assert exc_info.value.status_code == 404
    assert str(unknown_id) in exc_info.value.detail


@pytest.mark.asyncio
async def test_list_tournament_agents_empty_teams(
    tournament_id: UUID,
    mock_orchestrator: MagicMock,
) -> None:
    """Tournament with no teams should return an empty list without error."""
    from packages.api.src.routes.agents import list_tournament_agents

    mock_orchestrator._active_tournaments[tournament_id].team_ids = []

    mgr = MagicMock()
    mgr.get_team_agents = AsyncMock(return_value=[])

    result = await list_tournament_agents(
        tournament_id=tournament_id,
        orchestrator=mock_orchestrator,
        agent_manager=mgr,
    )

    assert result == []


# ---------------------------------------------------------------------------
# list_team_agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_team_agents_returns_team_agents(
    tournament_id: UUID,
    team_id_a: UUID,
    mock_orchestrator: MagicMock,
    mock_agent_manager: MagicMock,
) -> None:
    """Should return agents belonging only to the requested team."""
    from packages.api.src.routes.agents import list_team_agents

    result = await list_team_agents(
        tournament_id=tournament_id,
        team_id=team_id_a,
        orchestrator=mock_orchestrator,
        agent_manager=mock_agent_manager,
    )

    assert len(result) == 1
    assert result[0].team_id == team_id_a


@pytest.mark.asyncio
async def test_list_team_agents_unknown_tournament_raises_404(
    team_id_a: UUID,
    mock_orchestrator: MagicMock,
    mock_agent_manager: MagicMock,
) -> None:
    """Should raise 404 when the tournament does not exist."""
    from fastapi import HTTPException

    from packages.api.src.routes.agents import list_team_agents

    with pytest.raises(HTTPException) as exc_info:
        await list_team_agents(
            tournament_id=uuid4(),
            team_id=team_id_a,
            orchestrator=mock_orchestrator,
            agent_manager=mock_agent_manager,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_team_agents_unknown_team_raises_404(
    tournament_id: UUID,
    mock_orchestrator: MagicMock,
    mock_agent_manager: MagicMock,
) -> None:
    """Should raise 404 when the team is not part of the tournament."""
    from fastapi import HTTPException

    from packages.api.src.routes.agents import list_team_agents

    unknown_team = uuid4()
    with pytest.raises(HTTPException) as exc_info:
        await list_team_agents(
            tournament_id=tournament_id,
            team_id=unknown_team,
            orchestrator=mock_orchestrator,
            agent_manager=mock_agent_manager,
        )

    assert exc_info.value.status_code == 404
    assert str(unknown_team) in exc_info.value.detail


@pytest.mark.asyncio
async def test_list_team_agents_empty_team_returns_empty_list(
    tournament_id: UUID,
    team_id_a: UUID,
    mock_orchestrator: MagicMock,
) -> None:
    """Should return empty list when a team has no agents yet."""
    from packages.api.src.routes.agents import list_team_agents

    mgr = MagicMock()
    mgr.get_team_agents = AsyncMock(return_value=[])

    result = await list_team_agents(
        tournament_id=tournament_id,
        team_id=team_id_a,
        orchestrator=mock_orchestrator,
        agent_manager=mgr,
    )

    assert result == []


@pytest.mark.asyncio
async def test_list_team_agents_multiple_agents_per_team(
    tournament_id: UUID,
    team_id_a: UUID,
    mock_orchestrator: MagicMock,
) -> None:
    """Should return all agents when a team has multiple members."""
    from packages.api.src.routes.agents import list_team_agents

    agents = [
        make_agent(team_id=team_id_a, tournament_id=tournament_id, role=AgentRole.ARCHITECT),
        make_agent(team_id=team_id_a, tournament_id=tournament_id, role=AgentRole.BUILDER),
        make_agent(team_id=team_id_a, tournament_id=tournament_id, role=AgentRole.TESTER),
    ]

    mgr = MagicMock()
    mgr.get_team_agents = AsyncMock(return_value=agents)

    result = await list_team_agents(
        tournament_id=tournament_id,
        team_id=team_id_a,
        orchestrator=mock_orchestrator,
        agent_manager=mgr,
    )

    assert len(result) == 3
    roles = {r.role for r in result}
    assert AgentRole.ARCHITECT in roles
    assert AgentRole.BUILDER in roles
    assert AgentRole.TESTER in roles
