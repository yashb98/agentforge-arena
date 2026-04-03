"""
AgentForge Arena — Core Domain Types

All shared Pydantic models used across the monorepo.
These are the source of truth for data shapes.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Enums
# ============================================================


class TournamentFormat(str, Enum):
    DUEL = "duel"
    STANDARD = "standard"
    LEAGUE = "league"
    GRAND_PRIX = "grand_prix"
    # Milestone-driven: no auto phase timers; advance via API only
    MARATHON = "marathon"


class TournamentPhase(str, Enum):
    PREP = "prep"
    RESEARCH = "research"
    ARCHITECTURE = "architecture"
    BUILD = "build"
    CROSS_REVIEW = "cross_review"
    FIX = "fix"
    JUDGE = "judge"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class AgentRole(str, Enum):
    ARCHITECT = "architect"
    BUILDER = "builder"
    FRONTEND = "frontend"
    TESTER = "tester"
    CRITIC = "critic"
    RESEARCHER = "researcher"


class AgentStatus(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    CODING = "coding"
    TESTING = "testing"
    REVIEWING = "reviewing"
    WAITING = "waiting"
    ERROR = "error"
    TERMINATED = "terminated"


class ModelProvider(str, Enum):
    CLAUDE_OPUS_4_6 = "claude-opus-4-6"
    CLAUDE_SONNET_4_6 = "claude-sonnet-4-6"
    CLAUDE_HAIKU_4_5 = "claude-haiku-4-5"
    GPT_5 = "gpt-5"
    GEMINI_3_PRO = "gemini-3-pro"
    QWEN3_72B = "qwen3-72b"
    QWEN3_32B = "qwen3-32b"
    QWEN3_8B = "qwen3-8b"


class ChallengeCategory(str, Enum):
    SAAS_APP = "saas_app"
    CLI_TOOL = "cli_tool"
    AI_AGENT = "ai_agent"
    API_SERVICE = "api_service"
    REAL_TIME = "real_time"
    DATA_PIPELINE = "data_pipeline"


class ChallengeDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"


class MessageType(str, Enum):
    TASK_ASSIGNMENT = "task_assignment"
    TASK_COMPLETE = "task_complete"
    REVIEW_REQUEST = "review_request"
    REVIEW_FEEDBACK = "review_feedback"
    BUG_REPORT = "bug_report"
    ARCHITECTURE_UPDATE = "architecture_update"
    HELP_REQUEST = "help_request"
    STATUS_UPDATE = "status_update"
    CONFLICT_RESOLUTION = "conflict_resolution"


# ============================================================
# Core Models
# ============================================================


class AgentConfig(BaseModel):
    """Configuration for a single agent within a team."""

    model_config = ConfigDict(strict=True)

    role: AgentRole
    model: ModelProvider
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=8192, ge=256, le=200000)
    timeout_seconds: int = Field(default=300, ge=30, le=900)
    tools: list[str] = Field(default_factory=list, description="Allowed tool patterns")


class TeamConfig(BaseModel):
    """Configuration for a team of agents."""

    model_config = ConfigDict(strict=True)

    name: str = Field(min_length=1, max_length=100)
    preset: str = Field(default="balanced", description="Preset config name")
    agents: list[AgentConfig] = Field(min_length=3, max_length=8)
    strategy: dict[str, object] = Field(default_factory=dict)
    sandbox_memory: str = "4g"
    sandbox_cpus: int = Field(default=2, ge=1, le=8)
    # Hierarchical teams (P1): optional parent for sub-team / pod coordination
    parent_team_id: UUID | None = Field(
        default=None,
        description="When set, this team reports to a parent team in the same tournament",
    )


class TournamentConfig(BaseModel):
    """Configuration for creating a tournament."""

    model_config = ConfigDict(strict=True)

    format: TournamentFormat
    challenge_id: str | None = None
    teams: list[TeamConfig] = Field(min_length=2, max_length=8)
    phase_timings: dict[TournamentPhase, int] | None = None  # Override default timings (seconds)
    budget_limit_usd: float = Field(default=500.0, ge=10.0, le=5000.0)


# ============================================================
# Domain Entities
# ============================================================


class Tournament(BaseModel):
    """A tournament instance."""

    id: UUID = Field(default_factory=uuid4)
    format: TournamentFormat
    current_phase: TournamentPhase = TournamentPhase.PREP
    challenge_id: str
    config: TournamentConfig
    team_ids: list[UUID] = Field(default_factory=list)
    current_round: int = 1
    total_rounds: int = 1
    started_at: datetime | None = None
    completed_at: datetime | None = None
    winner_team_id: UUID | None = None
    total_cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Team(BaseModel):
    """A team participating in a tournament."""

    id: UUID = Field(default_factory=uuid4)
    tournament_id: UUID
    name: str
    config: TeamConfig
    sandbox_id: str | None = None
    agent_ids: list[UUID] = Field(default_factory=list)
    elo_rating: float = 1500.0
    total_cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Agent(BaseModel):
    """An agent instance within a team."""

    id: UUID = Field(default_factory=uuid4)
    team_id: UUID
    tournament_id: UUID
    role: AgentRole
    model: ModelProvider
    status: AgentStatus = AgentStatus.IDLE
    process_id: int | None = None
    total_tokens_used: int = 0
    total_cost_usd: float = 0.0
    actions_count: int = 0
    errors_count: int = 0
    last_heartbeat: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Challenge(BaseModel):
    """A hackathon challenge for teams to build."""

    id: str = Field(description="URL-safe identifier, e.g., 'url-shortener-saas'")
    title: str
    description: str
    category: ChallengeCategory
    difficulty: ChallengeDifficulty
    time_limit_minutes: int = Field(default=90, ge=30, le=240)
    requirements: list[str] = Field(min_length=1, description="Functional requirements")
    hidden_test_hints: list[str] = Field(
        default_factory=list, description="Hints about hidden test suite (shown in brief)"
    )
    scoring_weights: dict[str, float] | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# Event Types
# ============================================================


class ArenaEvent(BaseModel):
    """Base event published to the event bus."""

    model_config = ConfigDict(strict=True)

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = Field(description="Dot-notation event type, e.g., tournament.phase.changed")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: int = Field(default=1, description="Schema version for event evolution")
    source: str = Field(description="Service/module that published the event")
    correlation_id: UUID = Field(
        default_factory=uuid4, description="Links related events across services"
    )
    tournament_id: UUID | None = None
    team_id: UUID | None = None
    agent_id: UUID | None = None
    payload: dict[str, object] = Field(default_factory=dict)


# ============================================================
# Agent Communication
# ============================================================


class AgentMessage(BaseModel):
    """Message between agents via the mailbox protocol."""

    model_config = ConfigDict(strict=True)

    id: UUID = Field(default_factory=uuid4)
    from_agent: AgentRole
    to_agent: AgentRole | None = None  # None = broadcast to all
    message_type: MessageType
    priority: str = Field(default="normal", pattern=r"^(critical|high|normal|low)$")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: UUID = Field(default_factory=uuid4)
    payload: dict[str, object] = Field(default_factory=dict)
    read: bool = False


# ============================================================
# Scoring
# ============================================================


class JudgeScore(BaseModel):
    """Score from a single judge dimension."""

    dimension: str  # functionality, code_quality, test_coverage, ux_design, architecture, innovation
    score: float = Field(ge=0.0, le=100.0)
    weight: float = Field(ge=0.0, le=1.0)
    judge_type: str  # automated, llm, cross_review
    details: str = ""


class MatchResult(BaseModel):
    """Result of a match between two teams."""

    id: UUID = Field(default_factory=uuid4)
    tournament_id: UUID
    round_number: int
    team_a_id: UUID
    team_b_id: UUID
    team_a_scores: list[JudgeScore] = Field(default_factory=list)
    team_b_scores: list[JudgeScore] = Field(default_factory=list)
    team_a_total: float = 0.0
    team_b_total: float = 0.0
    winner_team_id: UUID | None = None
    is_draw: bool = False
    judged_at: datetime = Field(default_factory=datetime.utcnow)


class LeaderboardEntry(BaseModel):
    """A single entry on the leaderboard."""

    team_config_name: str
    elo_rating: float
    elo_ci_lower: float
    elo_ci_upper: float
    matches_played: int
    wins: int
    losses: int
    draws: int
    win_rate: float
    avg_score: float
    last_match: datetime | None = None
