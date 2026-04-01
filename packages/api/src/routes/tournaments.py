"""
AgentForge Arena — Tournament Route Handlers

CRUD and lifecycle endpoints for tournaments.  All business logic is
delegated to the TournamentOrchestrator injected via Depends().

Routes:
    POST   /tournaments                → create a new tournament (201)
    GET    /tournaments                → paginated list of tournaments (200)
    GET    /tournaments/{id}           → single tournament detail (200 | 404)
    POST   /tournaments/{id}/start     → transition to RESEARCH phase (200 | 400)
    POST   /tournaments/{id}/cancel    → cancel an active tournament (200 | 404)
"""

from __future__ import annotations

import logging
from uuid import UUID

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import ORJSONResponse

from packages.api.src.dependencies import get_orchestrator
from packages.shared.src.types.models import (
    Team,
    Tournament,
    TournamentConfig,
    TournamentPhase,
)
from packages.shared.src.types.responses import (
    TeamSummary,
    TournamentListResponse,
    TournamentResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


# ============================================================
# Helpers
# ============================================================


def _tournament_to_response(
    tournament: Tournament,
    teams: list[Team] | None = None,
) -> TournamentResponse:
    """Convert a domain Tournament entity to a TournamentResponse.

    Args:
        tournament: The domain entity returned by the orchestrator.
        teams: Optional list of Team objects for this tournament.  When omitted,
               team summaries are built from ``tournament.team_ids`` with zeroed
               counts (the caller should supply teams if they are available).

    Returns:
        A fully-populated TournamentResponse ready for serialisation.
    """
    if teams:
        team_summaries = [
            TeamSummary(
                id=team.id,
                name=team.name,
                agent_count=len(team.agent_ids),
                total_cost_usd=team.total_cost_usd,
            )
            for team in teams
        ]
    else:
        # Fallback: minimal summaries derived from team IDs alone
        team_summaries = [
            TeamSummary(
                id=tid,
                name=f"team-{tid}",
                agent_count=0,
                total_cost_usd=0.0,
            )
            for tid in tournament.team_ids
        ]

    return TournamentResponse(
        id=tournament.id,
        format=tournament.format,
        current_phase=tournament.current_phase,
        challenge_id=tournament.challenge_id,
        teams=team_summaries,
        total_cost_usd=tournament.total_cost_usd,
        started_at=tournament.started_at,
        completed_at=tournament.completed_at,
        winner_team_id=tournament.winner_team_id,
    )


# ============================================================
# Endpoints
# ============================================================


@router.post(
    "",
    status_code=201,
    response_model=TournamentResponse,
    summary="Create a tournament",
    response_description="The newly created tournament in PREP phase.",
)
async def create_tournament(
    payload: dict[str, Any] = Body(...),
    orchestrator: object = Depends(get_orchestrator),
) -> TournamentResponse:
    """Create a new tournament from the supplied configuration.

    The tournament is initialised in the **PREP** phase.  Call
    ``POST /tournaments/{id}/start`` to begin execution.

    Args:
        payload: Raw JSON body validated into TournamentConfig.
        orchestrator: Injected TournamentOrchestrator instance.

    Returns:
        The created tournament representation.

    Raises:
        HTTPException 400: If the configuration is invalid or rejected by the orchestrator.
    """
    try:
        config = TournamentConfig.model_validate(payload)
        tournament: Tournament = await orchestrator.create_tournament(config)
    except ValueError as exc:
        logger.warning("Invalid tournament config: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error creating tournament")
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    logger.info("Tournament created: %s (format=%s)", tournament.id, tournament.format)
    return _tournament_to_response(tournament)


@router.get(
    "",
    response_model=TournamentListResponse,
    summary="List tournaments",
    response_description="Paginated list of tournaments.",
)
async def list_tournaments(
    limit: int = Query(default=20, ge=1, le=100, description="Max records to return"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
    orchestrator: object = Depends(get_orchestrator),
) -> TournamentListResponse:
    """Return a paginated list of all tournaments (most recent first).

    Args:
        limit: Maximum number of records to return (1–100, default 20).
        offset: Number of records to skip for pagination (default 0).
        orchestrator: Injected TournamentOrchestrator instance.

    Returns:
        Paginated collection of tournament summaries.
    """
    active: dict[UUID, Tournament] = getattr(orchestrator, "_active_tournaments", {})
    all_tournaments: list[Tournament] = list(active.values())

    total = len(all_tournaments)
    page = all_tournaments[offset : offset + limit]

    return TournamentListResponse(
        tournaments=[_tournament_to_response(t) for t in page],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{tournament_id}",
    response_model=TournamentResponse,
    summary="Get tournament detail",
    response_description="Single tournament record.",
)
async def get_tournament(
    tournament_id: UUID,
    orchestrator: object = Depends(get_orchestrator),
) -> TournamentResponse:
    """Retrieve a single tournament by its UUID.

    Args:
        tournament_id: The UUID of the tournament to retrieve.
        orchestrator: Injected TournamentOrchestrator instance.

    Returns:
        The tournament record.

    Raises:
        HTTPException 404: If no tournament with the given ID exists.
    """
    active: dict[UUID, Tournament] = getattr(orchestrator, "_active_tournaments", {})
    tournament = active.get(tournament_id)

    if tournament is None:
        raise HTTPException(status_code=404, detail=f"Tournament {tournament_id} not found")

    return _tournament_to_response(tournament)


@router.post(
    "/{tournament_id}/start",
    response_model=TournamentResponse,
    summary="Start a tournament",
    response_description="The tournament after transitioning out of PREP.",
)
async def start_tournament(
    tournament_id: UUID,
    orchestrator: object = Depends(get_orchestrator),
) -> TournamentResponse:
    """Transition a tournament from PREP to the RESEARCH phase.

    The tournament must exist and be in the **PREP** phase; otherwise a 400
    is returned.

    Args:
        tournament_id: UUID of the tournament to start.
        orchestrator: Injected TournamentOrchestrator instance.

    Returns:
        The updated tournament record.

    Raises:
        HTTPException 400: If the tournament cannot be started (wrong phase,
            validation failure, or orchestrator rejection).
        HTTPException 404: If the tournament does not exist.
    """
    # Verify existence before calling orchestrator
    active: dict[UUID, Tournament] = getattr(orchestrator, "_active_tournaments", {})
    if tournament_id not in active:
        raise HTTPException(status_code=404, detail=f"Tournament {tournament_id} not found")

    current_phase = active[tournament_id].current_phase
    if current_phase != TournamentPhase.PREP:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Tournament {tournament_id} cannot be started: "
                f"current phase is '{current_phase}', expected 'prep'."
            ),
        )

    try:
        tournament: Tournament = await orchestrator.start_tournament(tournament_id)
    except ValueError as exc:
        logger.warning("Cannot start tournament %s: %s", tournament_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error starting tournament %s", tournament_id)
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    logger.info("Tournament started: %s", tournament_id)
    return _tournament_to_response(tournament)


@router.post(
    "/{tournament_id}/cancel",
    response_model=TournamentResponse,
    summary="Cancel a tournament",
    response_description="The tournament after cancellation.",
)
async def cancel_tournament(
    tournament_id: UUID,
    orchestrator: object = Depends(get_orchestrator),
) -> TournamentResponse:
    """Cancel an active tournament.

    Sets the tournament phase to **CANCELLED** and releases any provisioned
    sandboxes.  Completed tournaments cannot be cancelled.

    Args:
        tournament_id: UUID of the tournament to cancel.
        orchestrator: Injected TournamentOrchestrator instance.

    Returns:
        The updated (cancelled) tournament record.

    Raises:
        HTTPException 404: If the tournament does not exist.
        HTTPException 400: If the tournament is already in a terminal state.
    """
    active: dict[UUID, Tournament] = getattr(orchestrator, "_active_tournaments", {})
    if tournament_id not in active:
        raise HTTPException(status_code=404, detail=f"Tournament {tournament_id} not found")

    current_phase = active[tournament_id].current_phase
    terminal_phases = {TournamentPhase.COMPLETE, TournamentPhase.CANCELLED}
    if current_phase in terminal_phases:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Tournament {tournament_id} is already in terminal phase '{current_phase}' "
                "and cannot be cancelled."
            ),
        )

    try:
        tournament = active[tournament_id]
        # Delegate cancellation to orchestrator if it exposes the method,
        # otherwise mutate the phase directly (graceful degradation).
        if hasattr(orchestrator, "cancel_tournament"):
            tournament = await orchestrator.cancel_tournament(tournament_id)  # type: ignore[assignment]
        else:
            # Minimal in-process cancellation
            object.__setattr__(tournament, "current_phase", TournamentPhase.CANCELLED)
    except Exception as exc:
        logger.exception("Unexpected error cancelling tournament %s", tournament_id)
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    logger.info("Tournament cancelled: %s", tournament_id)
    return _tournament_to_response(tournament)
