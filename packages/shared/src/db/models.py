"""
AgentForge Arena — Database ORM Models

SQLAlchemy 2.0 async models for all persistent entities.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.shared.src.db.base import Base


class TournamentDB(Base):
    """Tournament table."""

    __tablename__ = "tournaments"

    format: Mapped[str] = mapped_column(String(20), nullable=False)
    current_phase: Mapped[str] = mapped_column(String(20), default="prep")
    challenge_id: Mapped[str] = mapped_column(String(100), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    current_round: Mapped[int] = mapped_column(Integer, default=1)
    total_rounds: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    winner_team_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # Relationships
    teams: Mapped[list[TeamDB]] = relationship(back_populates="tournament", lazy="selectin")
    matches: Mapped[list[MatchResultDB]] = relationship(back_populates="tournament", lazy="selectin")


class TeamDB(Base):
    """Team table."""

    __tablename__ = "teams"

    tournament_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tournaments.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sandbox_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    elo_rating: Mapped[float] = mapped_column(Float, default=1500.0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # Relationships
    tournament: Mapped[TournamentDB] = relationship(back_populates="teams")
    agents: Mapped[list[AgentDB]] = relationship(back_populates="team", lazy="selectin")


class AgentDB(Base):
    """Agent table."""

    __tablename__ = "agents"

    team_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False, index=True
    )
    tournament_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tournaments.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="idle")
    process_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    actions_count: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    last_heartbeat: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    team: Mapped[TeamDB] = relationship(back_populates="agents")


class ChallengeDB(Base):
    """Challenge table."""

    __tablename__ = "challenges"

    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    time_limit_minutes: Mapped[int] = mapped_column(Integer, default=90)
    requirements: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    hidden_tests: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    scoring_weights: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    times_used: Mapped[int] = mapped_column(Integer, default=0)


class MatchResultDB(Base):
    """Match result table."""

    __tablename__ = "match_results"

    tournament_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tournaments.id"), nullable=False, index=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    team_a_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    team_b_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    team_a_scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    team_b_scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    team_a_total: Mapped[float] = mapped_column(Float, default=0.0)
    team_b_total: Mapped[float] = mapped_column(Float, default=0.0)
    winner_team_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    is_draw: Mapped[bool] = mapped_column(Boolean, default=False)
    cross_review_a: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cross_review_b: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    replay_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    tournament: Mapped[TournamentDB] = relationship(back_populates="matches")


class EloRatingDB(Base):
    """ELO rating history table."""

    __tablename__ = "elo_ratings"

    config_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    rating: Mapped[float] = mapped_column(Float, default=1500.0)
    ci_lower: Mapped[float] = mapped_column(Float, default=1400.0)
    ci_upper: Mapped[float] = mapped_column(Float, default=1600.0)
    matches_played: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(
        String(50), default="overall",
    )  # Rating category: overall, per_role, per_model
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
