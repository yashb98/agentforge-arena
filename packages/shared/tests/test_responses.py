"""Tests for API response Pydantic models."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

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
from packages.shared.src.types.responses import (
    AgentResponse,
    ChallengeListResponse,
    ChallengeResponse,
    LeaderboardResponse,
    TeamSummary,
    TournamentListResponse,
    TournamentResponse,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def team_summary() -> TeamSummary:
    """A valid TeamSummary fixture."""
    return TeamSummary(
        id=uuid4(),
        name="Alpha Team",
        agent_count=5,
        total_cost_usd=12.50,
    )


@pytest.fixture
def tournament_response(team_summary: TeamSummary) -> TournamentResponse:
    """A valid TournamentResponse fixture."""
    return TournamentResponse(
        id=uuid4(),
        format=TournamentFormat.DUEL,
        current_phase=TournamentPhase.BUILD,
        challenge_id="url-shortener-saas",
        teams=[team_summary],
        total_cost_usd=12.50,
        started_at=datetime.now(tz=timezone.utc),
    )


@pytest.fixture
def agent_response() -> AgentResponse:
    """A valid AgentResponse fixture."""
    return AgentResponse(
        id=uuid4(),
        team_id=uuid4(),
        role=AgentRole.BUILDER,
        model=ModelProvider.CLAUDE_SONNET_4_6,
        status=AgentStatus.CODING,
        total_tokens_used=150000,
        total_cost_usd=3.75,
        actions_count=42,
        errors_count=1,
        last_heartbeat=datetime.now(tz=timezone.utc),
    )


@pytest.fixture
def challenge_response() -> ChallengeResponse:
    """A valid ChallengeResponse fixture."""
    return ChallengeResponse(
        id="url-shortener-saas",
        title="Build a URL Shortener SaaS",
        description="Create a production-grade URL shortener with analytics.",
        category=ChallengeCategory.SAAS_APP,
        difficulty=ChallengeDifficulty.MEDIUM,
        time_limit_minutes=90,
        requirements=["Shorten URLs", "Track click analytics", "Custom slugs"],
        tags=["web", "api", "database"],
    )


@pytest.fixture
def leaderboard_entry() -> LeaderboardEntry:
    """A valid LeaderboardEntry fixture."""
    return LeaderboardEntry(
        team_config_name="balanced",
        elo_rating=1620.0,
        elo_ci_lower=1580.0,
        elo_ci_upper=1660.0,
        matches_played=10,
        wins=7,
        losses=2,
        draws=1,
        win_rate=0.7,
        avg_score=82.5,
        last_match=datetime.now(tz=timezone.utc),
    )


# ============================================================
# TeamSummary
# ============================================================


class TestTeamSummary:
    """Tests for TeamSummary model."""

    def test_create_valid_team_summary(self, team_summary: TeamSummary) -> None:
        """Valid TeamSummary should instantiate correctly."""
        assert team_summary.name == "Alpha Team"
        assert team_summary.agent_count == 5
        assert team_summary.total_cost_usd == 12.50
        assert team_summary.id is not None

    def test_team_summary_serialization_roundtrip(self, team_summary: TeamSummary) -> None:
        """TeamSummary should survive JSON serialization."""
        json_str = team_summary.model_dump_json()
        restored = TeamSummary.model_validate_json(json_str)
        assert restored.id == team_summary.id
        assert restored.name == team_summary.name
        assert restored.agent_count == team_summary.agent_count
        assert restored.total_cost_usd == team_summary.total_cost_usd

    def test_team_summary_model_dump_json_mode(self, team_summary: TeamSummary) -> None:
        """model_dump with json mode should produce serializable dict."""
        data = team_summary.model_dump(mode="json")
        assert isinstance(data["id"], str)
        assert data["name"] == "Alpha Team"


# ============================================================
# TournamentResponse
# ============================================================


class TestTournamentResponse:
    """Tests for TournamentResponse model."""

    def test_create_valid_tournament_response(
        self, tournament_response: TournamentResponse
    ) -> None:
        """Valid TournamentResponse should instantiate with all required fields."""
        assert tournament_response.format == TournamentFormat.DUEL
        assert tournament_response.current_phase == TournamentPhase.BUILD
        assert tournament_response.challenge_id == "url-shortener-saas"
        assert len(tournament_response.teams) == 1
        assert tournament_response.winner_team_id is None

    def test_tournament_response_optional_fields_default_none(
        self, team_summary: TeamSummary
    ) -> None:
        """Optional fields should default to None."""
        response = TournamentResponse(
            id=uuid4(),
            format=TournamentFormat.STANDARD,
            current_phase=TournamentPhase.PREP,
            challenge_id="my-challenge",
            teams=[team_summary],
            total_cost_usd=0.0,
        )
        assert response.started_at is None
        assert response.completed_at is None
        assert response.winner_team_id is None

    def test_tournament_response_with_winner(self, team_summary: TeamSummary) -> None:
        """TournamentResponse should accept winner_team_id."""
        winner_id = team_summary.id
        response = TournamentResponse(
            id=uuid4(),
            format=TournamentFormat.DUEL,
            current_phase=TournamentPhase.COMPLETE,
            challenge_id="test-challenge",
            teams=[team_summary],
            total_cost_usd=50.0,
            winner_team_id=winner_id,
            completed_at=datetime.now(tz=timezone.utc),
        )
        assert response.winner_team_id == winner_id
        assert response.completed_at is not None

    def test_tournament_response_serialization(
        self, tournament_response: TournamentResponse
    ) -> None:
        """TournamentResponse should serialize and deserialize correctly."""
        json_str = tournament_response.model_dump_json()
        restored = TournamentResponse.model_validate_json(json_str)
        assert restored.id == tournament_response.id
        assert restored.format == tournament_response.format
        assert restored.current_phase == tournament_response.current_phase
        assert len(restored.teams) == 1

    def test_tournament_response_contains_team_summaries(
        self, tournament_response: TournamentResponse
    ) -> None:
        """teams field should be a list of TeamSummary."""
        assert isinstance(tournament_response.teams[0], TeamSummary)


# ============================================================
# TournamentListResponse
# ============================================================


class TestTournamentListResponse:
    """Tests for TournamentListResponse model."""

    def test_create_with_defaults(self, tournament_response: TournamentResponse) -> None:
        """Default offset and limit should be applied."""
        list_resp = TournamentListResponse(
            tournaments=[tournament_response],
            total=1,
        )
        assert list_resp.offset == 0
        assert list_resp.limit == 20
        assert list_resp.total == 1

    def test_create_with_pagination(self, tournament_response: TournamentResponse) -> None:
        """Pagination params should be stored correctly."""
        list_resp = TournamentListResponse(
            tournaments=[tournament_response],
            total=100,
            offset=20,
            limit=10,
        )
        assert list_resp.offset == 20
        assert list_resp.limit == 10

    def test_empty_tournaments_list(self) -> None:
        """Empty list of tournaments should be valid."""
        list_resp = TournamentListResponse(tournaments=[], total=0)
        assert len(list_resp.tournaments) == 0
        assert list_resp.total == 0

    def test_tournament_list_serialization(
        self, tournament_response: TournamentResponse
    ) -> None:
        """TournamentListResponse should serialize correctly."""
        list_resp = TournamentListResponse(
            tournaments=[tournament_response],
            total=1,
        )
        data = list_resp.model_dump(mode="json")
        assert data["total"] == 1
        assert len(data["tournaments"]) == 1
        assert data["offset"] == 0
        assert data["limit"] == 20


# ============================================================
# AgentResponse
# ============================================================


class TestAgentResponse:
    """Tests for AgentResponse model."""

    def test_create_valid_agent_response(self, agent_response: AgentResponse) -> None:
        """Valid AgentResponse should have all expected fields."""
        assert agent_response.role == AgentRole.BUILDER
        assert agent_response.model == ModelProvider.CLAUDE_SONNET_4_6
        assert agent_response.status == AgentStatus.CODING
        assert agent_response.total_tokens_used == 150000
        assert agent_response.actions_count == 42
        assert agent_response.errors_count == 1

    def test_agent_response_optional_heartbeat(self) -> None:
        """last_heartbeat should be optional and default to None."""
        response = AgentResponse(
            id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.ARCHITECT,
            model=ModelProvider.CLAUDE_OPUS_4_6,
            status=AgentStatus.IDLE,
            total_tokens_used=0,
            total_cost_usd=0.0,
            actions_count=0,
            errors_count=0,
        )
        assert response.last_heartbeat is None

    def test_agent_response_serialization_roundtrip(
        self, agent_response: AgentResponse
    ) -> None:
        """AgentResponse should survive JSON roundtrip."""
        json_str = agent_response.model_dump_json()
        restored = AgentResponse.model_validate_json(json_str)
        assert restored.id == agent_response.id
        assert restored.role == agent_response.role
        assert restored.status == agent_response.status
        assert restored.total_tokens_used == agent_response.total_tokens_used

    def test_agent_response_enum_values(self, agent_response: AgentResponse) -> None:
        """Enum fields should serialize to their string values."""
        data = agent_response.model_dump(mode="json")
        assert data["role"] == "builder"
        assert data["model"] == "claude-sonnet-4-6"
        assert data["status"] == "coding"


# ============================================================
# LeaderboardResponse
# ============================================================


class TestLeaderboardResponse:
    """Tests for LeaderboardResponse model."""

    def test_create_valid_leaderboard_response(
        self, leaderboard_entry: LeaderboardEntry
    ) -> None:
        """Valid LeaderboardResponse should instantiate correctly."""
        now = datetime.now(tz=timezone.utc)
        response = LeaderboardResponse(
            entries=[leaderboard_entry],
            total=1,
            updated_at=now,
        )
        assert response.total == 1
        assert len(response.entries) == 1
        assert response.updated_at == now

    def test_leaderboard_response_entries_are_leaderboard_entries(
        self, leaderboard_entry: LeaderboardEntry
    ) -> None:
        """entries field should contain LeaderboardEntry instances."""
        response = LeaderboardResponse(
            entries=[leaderboard_entry],
            total=1,
            updated_at=datetime.now(tz=timezone.utc),
        )
        entry = response.entries[0]
        assert isinstance(entry, LeaderboardEntry)
        assert entry.elo_rating == 1620.0
        assert entry.wins == 7

    def test_leaderboard_response_serialization(
        self, leaderboard_entry: LeaderboardEntry
    ) -> None:
        """LeaderboardResponse should serialize to JSON."""
        response = LeaderboardResponse(
            entries=[leaderboard_entry],
            total=1,
            updated_at=datetime.now(tz=timezone.utc),
        )
        data = response.model_dump(mode="json")
        assert data["total"] == 1
        assert len(data["entries"]) == 1
        assert data["entries"][0]["team_config_name"] == "balanced"

    def test_empty_leaderboard(self) -> None:
        """Empty leaderboard should be valid."""
        response = LeaderboardResponse(
            entries=[],
            total=0,
            updated_at=datetime.now(tz=timezone.utc),
        )
        assert len(response.entries) == 0


# ============================================================
# ChallengeResponse
# ============================================================


class TestChallengeResponse:
    """Tests for ChallengeResponse model."""

    def test_create_valid_challenge_response(
        self, challenge_response: ChallengeResponse
    ) -> None:
        """Valid ChallengeResponse should store all fields."""
        assert challenge_response.id == "url-shortener-saas"
        assert challenge_response.category == ChallengeCategory.SAAS_APP
        assert challenge_response.difficulty == ChallengeDifficulty.MEDIUM
        assert challenge_response.time_limit_minutes == 90
        assert len(challenge_response.requirements) == 3

    def test_challenge_response_tags_default_empty(self) -> None:
        """tags should default to an empty list."""
        response = ChallengeResponse(
            id="no-tags",
            title="No Tags Challenge",
            description="A challenge without tags.",
            category=ChallengeCategory.CLI_TOOL,
            difficulty=ChallengeDifficulty.EASY,
            time_limit_minutes=60,
            requirements=["Do something"],
        )
        assert response.tags == []

    def test_challenge_response_serialization_roundtrip(
        self, challenge_response: ChallengeResponse
    ) -> None:
        """ChallengeResponse should survive JSON roundtrip."""
        json_str = challenge_response.model_dump_json()
        restored = ChallengeResponse.model_validate_json(json_str)
        assert restored.id == challenge_response.id
        assert restored.category == challenge_response.category
        assert restored.requirements == challenge_response.requirements
        assert restored.tags == challenge_response.tags

    def test_challenge_response_enum_values(
        self, challenge_response: ChallengeResponse
    ) -> None:
        """Enum fields should serialize to string values."""
        data = challenge_response.model_dump(mode="json")
        assert data["category"] == "saas_app"
        assert data["difficulty"] == "medium"


# ============================================================
# ChallengeListResponse
# ============================================================


class TestChallengeListResponse:
    """Tests for ChallengeListResponse model."""

    def test_create_with_challenges(
        self, challenge_response: ChallengeResponse
    ) -> None:
        """ChallengeListResponse should hold a list of ChallengeResponse."""
        list_resp = ChallengeListResponse(
            challenges=[challenge_response],
            total=1,
        )
        assert list_resp.total == 1
        assert len(list_resp.challenges) == 1

    def test_empty_challenges_list(self) -> None:
        """Empty challenges list should be valid."""
        list_resp = ChallengeListResponse(challenges=[], total=0)
        assert len(list_resp.challenges) == 0
        assert list_resp.total == 0

    def test_challenge_list_serialization(
        self, challenge_response: ChallengeResponse
    ) -> None:
        """ChallengeListResponse should serialize correctly."""
        list_resp = ChallengeListResponse(
            challenges=[challenge_response],
            total=1,
        )
        data = list_resp.model_dump(mode="json")
        assert data["total"] == 1
        assert len(data["challenges"]) == 1
        assert data["challenges"][0]["id"] == "url-shortener-saas"

    def test_multiple_challenges(self, challenge_response: ChallengeResponse) -> None:
        """ChallengeListResponse should handle multiple entries."""
        second = ChallengeResponse(
            id="rest-api-service",
            title="Build a REST API Service",
            description="A robust REST API with auth.",
            category=ChallengeCategory.API_SERVICE,
            difficulty=ChallengeDifficulty.HARD,
            time_limit_minutes=120,
            requirements=["JWT auth", "CRUD endpoints", "OpenAPI docs"],
            tags=["api", "auth"],
        )
        list_resp = ChallengeListResponse(
            challenges=[challenge_response, second],
            total=2,
        )
        assert list_resp.total == 2
        assert list_resp.challenges[1].category == ChallengeCategory.API_SERVICE
