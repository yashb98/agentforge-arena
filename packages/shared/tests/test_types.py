"""Tests for shared domain types and event bus."""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio

from packages.shared.src.types.models import (
    AgentConfig,
    AgentMessage,
    AgentRole,
    ArenaEvent,
    Challenge,
    ChallengeCategory,
    ChallengeDifficulty,
    JudgeScore,
    MatchResult,
    MessageType,
    ModelProvider,
    TeamConfig,
    Tournament,
    TournamentConfig,
    TournamentFormat,
    TournamentPhase,
)


class TestTournamentConfig:
    """Tests for TournamentConfig validation."""

    def test_valid_duel_config(self, sample_tournament_config):
        """Valid duel config should pass validation."""
        assert sample_tournament_config.format == TournamentFormat.DUEL
        assert len(sample_tournament_config.teams) == 2

    def test_minimum_two_teams_required(self):
        """Config with fewer than 2 teams should fail."""
        with pytest.raises(Exception):  # Pydantic validation error
            TournamentConfig(
                format=TournamentFormat.DUEL,
                teams=[
                    TeamConfig(
                        name="Solo",
                        agents=[
                            AgentConfig(role=AgentRole.ARCHITECT, model=ModelProvider.CLAUDE_OPUS_4_6),
                            AgentConfig(role=AgentRole.BUILDER, model=ModelProvider.CLAUDE_SONNET_4_6),
                            AgentConfig(role=AgentRole.TESTER, model=ModelProvider.CLAUDE_HAIKU_4_5),
                        ],
                    )
                ],
            )

    def test_budget_limit_validation(self):
        """Budget must be between 10 and 5000."""
        with pytest.raises(Exception):
            TournamentConfig(
                format=TournamentFormat.DUEL,
                teams=[
                    TeamConfig(name="A", agents=[
                        AgentConfig(role=AgentRole.ARCHITECT, model=ModelProvider.CLAUDE_OPUS_4_6),
                        AgentConfig(role=AgentRole.BUILDER, model=ModelProvider.CLAUDE_SONNET_4_6),
                        AgentConfig(role=AgentRole.TESTER, model=ModelProvider.CLAUDE_HAIKU_4_5),
                    ]),
                    TeamConfig(name="B", agents=[
                        AgentConfig(role=AgentRole.ARCHITECT, model=ModelProvider.CLAUDE_OPUS_4_6),
                        AgentConfig(role=AgentRole.BUILDER, model=ModelProvider.CLAUDE_SONNET_4_6),
                        AgentConfig(role=AgentRole.TESTER, model=ModelProvider.CLAUDE_HAIKU_4_5),
                    ]),
                ],
                budget_limit_usd=5.0,  # Below minimum
            )


class TestAgentMessage:
    """Tests for agent message protocol."""

    def test_create_task_assignment(self):
        """Should create a valid task assignment message."""
        msg = AgentMessage(
            from_agent=AgentRole.ARCHITECT,
            to_agent=AgentRole.BUILDER,
            message_type=MessageType.TASK_ASSIGNMENT,
            priority="high",
            payload={
                "task_id": "TASK-001",
                "title": "Implement REST API",
                "acceptance_criteria": ["Tests pass", "Docs written"],
            },
        )
        assert msg.from_agent == AgentRole.ARCHITECT
        assert msg.to_agent == AgentRole.BUILDER
        assert msg.read is False
        assert msg.id is not None

    def test_broadcast_message_has_no_target(self):
        """Broadcast messages should have to_agent=None."""
        msg = AgentMessage(
            from_agent=AgentRole.ARCHITECT,
            to_agent=None,
            message_type=MessageType.ARCHITECTURE_UPDATE,
            payload={"message": "Stack changed to FastAPI"},
        )
        assert msg.to_agent is None

    def test_message_serialization_roundtrip(self):
        """Messages should survive JSON serialization."""
        msg = AgentMessage(
            from_agent=AgentRole.TESTER,
            to_agent=AgentRole.BUILDER,
            message_type=MessageType.BUG_REPORT,
            payload={"severity": "high", "file": "src/main.py"},
        )
        json_str = msg.model_dump_json()
        restored = AgentMessage.model_validate_json(json_str)
        assert restored.from_agent == msg.from_agent
        assert restored.payload == msg.payload
        assert restored.id == msg.id


class TestArenaEvent:
    """Tests for the event bus event model."""

    def test_create_event(self):
        """Should create a valid event."""
        event = ArenaEvent(
            event_type="tournament.phase.changed",
            source="core.orchestrator",
            tournament_id=uuid4(),
            payload={"previous": "prep", "current": "research"},
        )
        assert event.event_type == "tournament.phase.changed"
        assert event.version == 1
        assert event.event_id is not None

    def test_event_serialization(self):
        """Events should serialize to JSON cleanly."""
        event = ArenaEvent(
            event_type="agent.task.completed",
            source="agents.builder",
            payload={"task_id": "TASK-001"},
        )
        json_data = event.model_dump(mode="json")
        assert json_data["event_type"] == "agent.task.completed"
        assert isinstance(json_data["event_id"], str)


class TestJudgeScore:
    """Tests for scoring models."""

    def test_score_bounds(self):
        """Scores must be between 0 and 100."""
        score = JudgeScore(
            dimension="functionality",
            score=85.5,
            weight=0.30,
            judge_type="automated",
        )
        assert 0.0 <= score.score <= 100.0

    def test_invalid_score_raises(self):
        """Score outside bounds should fail validation."""
        with pytest.raises(Exception):
            JudgeScore(
                dimension="functionality",
                score=150.0,  # Over 100
                weight=0.30,
                judge_type="automated",
            )

    def test_match_result_winner_determination(self):
        """Match result should correctly identify the winner."""
        team_a = uuid4()
        team_b = uuid4()

        result = MatchResult(
            tournament_id=uuid4(),
            round_number=1,
            team_a_id=team_a,
            team_b_id=team_b,
            team_a_total=78.5,
            team_b_total=65.2,
            winner_team_id=team_a,
        )
        assert result.winner_team_id == team_a
        assert not result.is_draw


class TestChallenge:
    """Tests for challenge model."""

    def test_create_challenge(self, sample_challenge):
        """Should create a valid challenge."""
        assert sample_challenge.id == "url-shortener-saas"
        assert sample_challenge.category == ChallengeCategory.SAAS_APP
        assert len(sample_challenge.requirements) >= 1

    def test_challenge_requires_at_least_one_requirement(self):
        """Challenge must have at least one requirement."""
        with pytest.raises(Exception):
            Challenge(
                id="empty",
                title="Empty",
                description="No requirements",
                category=ChallengeCategory.CLI_TOOL,
                difficulty=ChallengeDifficulty.EASY,
                requirements=[],  # Empty — should fail
            )
