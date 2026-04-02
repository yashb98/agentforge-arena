"""Tests for MemoryPromoter (deterministic L1 -> L2 promotion)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from packages.memory.src.compression.promoter import MemoryPromoter
from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.working.models import WorkingState
from packages.shared.src.types.models import AgentRole, TournamentPhase


@pytest.fixture()
def promoter() -> MemoryPromoter:
    return MemoryPromoter()


@pytest.fixture()
def team_id():
    return uuid4()


@pytest.fixture()
def tournament_id():
    return uuid4()


class TestMemoryPromoter:
    """Tests for keyword-based promotion rules."""

    def test_adr_keyword_promotes(self, promoter, team_id, tournament_id) -> None:
        """Decisions with architecture keywords should promote as ADR."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=team_id,
            role=AgentRole.ARCHITECT,
            current_phase=TournamentPhase.ARCHITECTURE,
            recent_decisions=["Chose FastAPI over Flask for the REST API architecture"],
        )
        records = promoter.promote(state, tournament_id=tournament_id)
        adr_records = [r for r in records if r.record_type == RecordType.ADR]
        assert len(adr_records) >= 1

    def test_gotcha_keyword_promotes(self, promoter, team_id, tournament_id) -> None:
        """Decisions with gotcha keywords should promote as GOTCHA."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=team_id,
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            recent_decisions=["Careful: Redis drops idle connections, never forget retry wrapper"],
        )
        records = promoter.promote(state, tournament_id=tournament_id)
        gotcha_records = [r for r in records if r.record_type == RecordType.GOTCHA]
        assert len(gotcha_records) >= 1

    def test_coding_pattern_promotes(self, promoter, team_id, tournament_id) -> None:
        """Decisions with pattern keywords should promote as CODING_PATTERN."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=team_id,
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            recent_decisions=["Must use Depends() pattern for all FastAPI injection"],
        )
        records = promoter.promote(state, tournament_id=tournament_id)
        pattern_records = [r for r in records if r.record_type == RecordType.CODING_PATTERN]
        assert len(pattern_records) >= 1

    def test_tech_debt_promotes(self, promoter, team_id, tournament_id) -> None:
        """Decisions with bug/workaround keywords should promote as TECH_DEBT."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=team_id,
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            recent_decisions=["Bug: the ORM doesn't handle UUIDs, used a workaround"],
        )
        records = promoter.promote(state, tournament_id=tournament_id)
        debt_records = [r for r in records if r.record_type == RecordType.TECH_DEBT]
        assert len(debt_records) >= 1

    def test_no_promotion_for_routine(self, promoter, team_id, tournament_id) -> None:
        """Routine decisions should not be promoted."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=team_id,
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            recent_decisions=["Created file src/main.py", "Ran pytest"],
        )
        records = promoter.promote(state, tournament_id=tournament_id)
        assert len(records) == 0

    def test_frequent_files_promote_as_file_meta(
        self, promoter, team_id, tournament_id
    ) -> None:
        """Files touched > 3 times should promote as FILE_META."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=team_id,
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            recent_files_touched=[
                "src/api/auth.py",
                "src/api/auth.py",
                "src/api/auth.py",
                "src/api/auth.py",
                "src/models/user.py",
            ],
        )
        records = promoter.promote(state, tournament_id=tournament_id)
        file_records = [r for r in records if r.record_type == RecordType.FILE_META]
        assert len(file_records) >= 1
