"""
AgentForge Arena — Leaderboard Routes

ELO leaderboard endpoints. The leaderboard is populated after the first
tournament completes and grows as more matches are played.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.api.src.dependencies import get_db_session
from packages.shared.src.db.models import EloRatingDB
from packages.shared.src.types.models import LeaderboardEntry
from packages.shared.src.types.responses import LeaderboardResponse

router = APIRouter(prefix="/api/v1", tags=["leaderboard"])


@router.get(
    "/leaderboard",
    response_model=LeaderboardResponse,
    summary="Get the ELO leaderboard",
    description=(
        "Returns ranked leaderboard entries for all agent team configurations. "
        "The leaderboard is empty until at least one tournament has completed. "
        "Entries are ranked by ELO rating descending."
    ),
)
async def get_leaderboard(
    category: str = Query(
        default="overall",
        description="Rating category to filter by (overall, per_role, per_model)",
    ),
    db: AsyncSession = Depends(get_db_session),
) -> LeaderboardResponse:
    """Return the current ELO leaderboard from the database."""
    result = await db.execute(
        select(EloRatingDB)
        .where(EloRatingDB.category == category)
        .order_by(EloRatingDB.rating.desc())
    )
    rows = result.scalars().all()

    entries = [
        LeaderboardEntry(
            team_config_name=row.config_name,
            elo_rating=row.rating,
            elo_ci_lower=row.ci_lower,
            elo_ci_upper=row.ci_upper,
            matches_played=row.matches_played,
            wins=row.wins,
            losses=row.losses,
            draws=row.draws,
            win_rate=row.wins / max(row.matches_played, 1),
            avg_score=0.0,  # Computed from match history if needed
            last_match=row.updated_at,
        )
        for row in rows
    ]

    return LeaderboardResponse(
        entries=entries,
        total=len(entries),
        updated_at=datetime.utcnow(),
    )
