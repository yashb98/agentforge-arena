"""Tests for L1 Working Memory models."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from packages.memory.src.working.models import WorkingState
from packages.shared.src.types.models import AgentRole, TournamentPhase


class TestWorkingState:
    """Tests for WorkingState Pydantic model."""

    def test_create_minimal_working_state(self) -> None:
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
        )
        assert state.current_task is None
        assert state.current_file is None
        assert state.recent_decisions == []
        assert state.recent_files_touched == []
        assert state.active_errors == []
        assert state.context_summary == ""
        assert state.token_budget_used == 0

    def test_recent_decisions_capped_at_10(self) -> None:
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.ARCHITECT,
            current_phase=TournamentPhase.ARCHITECTURE,
            recent_decisions=[f"decision-{i}" for i in range(15)],
        )
        assert len(state.recent_decisions) == 10

    def test_recent_files_capped_at_20(self) -> None:
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            recent_files_touched=[f"src/file_{i}.py" for i in range(25)],
        )
        assert len(state.recent_files_touched) == 20

    def test_active_errors_uncapped(self) -> None:
        errors = [f"Error {i}" for i in range(100)]
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.TESTER,
            current_phase=TournamentPhase.BUILD,
            active_errors=errors,
        )
        assert len(state.active_errors) == 100

    def test_serialization_roundtrip(self) -> None:
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            current_task="Build auth API",
            recent_decisions=["Chose bcrypt"],
        )
        json_str = state.model_dump_json()
        restored = WorkingState.model_validate_json(json_str)
        assert restored.agent_id == state.agent_id
        assert restored.current_task == "Build auth API"
        assert restored.recent_decisions == ["Chose bcrypt"]

    def test_estimate_tokens_returns_positive_int(self) -> None:
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            current_task="Build the auth module",
            context_summary="We are building a FastAPI auth module with bcrypt.",
            recent_decisions=["Chose bcrypt over argon2"],
        )
        tokens = state.estimate_tokens()
        assert isinstance(tokens, int)
        assert tokens > 0
