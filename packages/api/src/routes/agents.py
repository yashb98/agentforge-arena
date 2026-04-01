"""
AgentForge Arena — Agent Routes

Endpoints for listing agents within a tournament or a specific team.
All agent state is managed by the AgentManager service.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from packages.api.src.dependencies import get_agent_manager, get_orchestrator
from packages.shared.src.types.models import Agent
from packages.shared.src.types.responses import AgentResponse

router = APIRouter(prefix="/api/v1/tournaments", tags=["agents"])


def _agent_to_response(agent: Agent) -> AgentResponse:
    """Convert domain Agent to API response model."""
    return AgentResponse(
        id=agent.id,
        team_id=agent.team_id,
        role=agent.role,
        model=agent.model,
        status=agent.status,
        total_tokens_used=agent.total_tokens_used,
        total_cost_usd=agent.total_cost_usd,
        actions_count=agent.actions_count,
        errors_count=agent.errors_count,
        last_heartbeat=agent.last_heartbeat,
    )


@router.get(
    "/{tournament_id}/agents",
    response_model=list[AgentResponse],
    summary="List all agents in a tournament",
    description=(
        "Returns every agent across all teams participating in the given tournament. "
        "Returns 404 if the tournament does not exist."
    ),
)
async def list_tournament_agents(
    tournament_id: UUID,
    orchestrator=Depends(get_orchestrator),  # noqa: ANN001
    agent_manager=Depends(get_agent_manager),  # noqa: ANN001
) -> list[AgentResponse]:
    """List all agents across all teams in a tournament."""
    active: dict[UUID, object] = orchestrator._active_tournaments  # type: ignore[assignment]
    if tournament_id not in active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tournament {tournament_id} not found",
        )

    tournament = active[tournament_id]
    team_ids: list[UUID] = tournament.team_ids  # type: ignore[union-attr]

    all_agents: list[AgentResponse] = []
    for team_id in team_ids:
        agents: list[Agent] = await agent_manager.get_team_agents(team_id)
        all_agents.extend(_agent_to_response(a) for a in agents)

    return all_agents


@router.get(
    "/{tournament_id}/teams/{team_id}/agents",
    response_model=list[AgentResponse],
    summary="List agents for a specific team",
    description=(
        "Returns all agents belonging to a specific team within a tournament. "
        "Returns 404 if the tournament or team does not exist."
    ),
)
async def list_team_agents(
    tournament_id: UUID,
    team_id: UUID,
    orchestrator=Depends(get_orchestrator),  # noqa: ANN001
    agent_manager=Depends(get_agent_manager),  # noqa: ANN001
) -> list[AgentResponse]:
    """List agents for a specific team within a tournament."""
    active: dict[UUID, object] = orchestrator._active_tournaments  # type: ignore[assignment]
    if tournament_id not in active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tournament {tournament_id} not found",
        )

    tournament = active[tournament_id]
    team_ids: list[UUID] = tournament.team_ids  # type: ignore[union-attr]

    if team_id not in team_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team {team_id} not found in tournament {tournament_id}",
        )

    agents: list[Agent] = await agent_manager.get_team_agents(team_id)
    return [_agent_to_response(a) for a in agents]
