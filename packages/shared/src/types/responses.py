"""
AgentForge Arena — API Response Models

Pydantic models used as FastAPI response schemas. These are read-optimised
views returned from route handlers — they are NOT domain entities.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from packages.shared.src.types.challenge_spec import ChallengeSpecDocument
from packages.shared.src.types.models import (
    AgentRole,
    AgentStatus,
    ChallengeCategory,
    ChallengeDifficulty,
    LeaderboardEntry,
    ModelProvider,
    TournamentFormat,
    TournamentPhase,
)


class TeamSummary(BaseModel):
    """Lightweight summary of a team, embedded in tournament responses."""

    id: UUID = Field(description="Unique team identifier")
    name: str = Field(description="Human-readable team name")
    agent_count: int = Field(description="Number of agents in the team")
    total_cost_usd: float = Field(description="Total API cost incurred by this team in USD")


class TournamentResponse(BaseModel):
    """Full tournament state returned by the API."""

    id: UUID = Field(description="Unique tournament identifier")
    format: TournamentFormat = Field(description="Tournament format (duel, standard, league, grand_prix)")
    current_phase: TournamentPhase = Field(description="Current execution phase of the tournament")
    challenge_id: str = Field(description="Identifier of the challenge being solved")
    teams: list[TeamSummary] = Field(description="Participating teams with summary stats")
    total_cost_usd: float = Field(description="Aggregated API cost across all teams in USD")
    started_at: datetime | None = Field(default=None, description="UTC timestamp when the tournament started")
    completed_at: datetime | None = Field(default=None, description="UTC timestamp when the tournament finished")
    winner_team_id: UUID | None = Field(default=None, description="ID of the winning team, if determined")


class TournamentListResponse(BaseModel):
    """Paginated list of tournaments."""

    tournaments: list[TournamentResponse] = Field(description="Page of tournament records")
    total: int = Field(description="Total number of tournaments matching the query")
    offset: int = Field(default=0, description="Number of records skipped (for pagination)")
    limit: int = Field(default=20, description="Maximum number of records returned per page")


class AgentResponse(BaseModel):
    """Detailed state of a single agent instance."""

    id: UUID = Field(description="Unique agent identifier")
    team_id: UUID = Field(description="ID of the team this agent belongs to")
    role: AgentRole = Field(description="Role of the agent within the team")
    model: ModelProvider = Field(description="LLM model powering this agent")
    status: AgentStatus = Field(description="Current operational status of the agent")
    total_tokens_used: int = Field(description="Cumulative number of tokens consumed")
    total_cost_usd: float = Field(description="Cumulative API cost for this agent in USD")
    actions_count: int = Field(description="Total number of tool-use actions performed")
    errors_count: int = Field(description="Total number of errors encountered")
    last_heartbeat: datetime | None = Field(
        default=None, description="UTC timestamp of the agent's most recent heartbeat"
    )


class LeaderboardResponse(BaseModel):
    """Ranked leaderboard of agent team configurations."""

    entries: list[LeaderboardEntry] = Field(description="Ranked leaderboard entries")
    total: int = Field(description="Total number of entries on the leaderboard")
    updated_at: datetime = Field(description="UTC timestamp of the last leaderboard update")


class ChallengeResponse(BaseModel):
    """A hackathon challenge as returned by the API."""

    id: str = Field(description="URL-safe challenge identifier, e.g., 'url-shortener-saas'")
    title: str = Field(description="Short human-readable title of the challenge")
    description: str = Field(description="Full description of what teams must build")
    category: ChallengeCategory = Field(description="Challenge category (saas_app, cli_tool, ai_agent, etc.)")
    difficulty: ChallengeDifficulty = Field(description="Difficulty level (easy, medium, hard, expert)")
    time_limit_minutes: int = Field(description="Time budget in minutes for each tournament phase")
    requirements: list[str] = Field(description="Functional requirements teams must satisfy")
    tags: list[str] = Field(default_factory=list, description="Searchable tags for filtering challenges")
    spec: ChallengeSpecDocument | None = Field(
        default=None,
        description="Validated challenge.spec.json when present in the library; null for legacy entries.",
    )


class ChallengeListResponse(BaseModel):
    """List of challenges returned by the API."""

    challenges: list[ChallengeResponse] = Field(description="Collection of challenge records")
    total: int = Field(description="Total number of available challenges")
