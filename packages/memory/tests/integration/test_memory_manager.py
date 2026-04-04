"""Integration tests for MemoryManager facade."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from packages.memory.src.manager import MemoryManager
from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.semantic.models import MemoryContext
from packages.memory.src.working.models import WorkingState
from packages.shared.src.types.models import AgentRole, TournamentPhase


@pytest.fixture
def mock_working_store():
    store = MagicMock()
    store.save = AsyncMock()
    store.load = AsyncMock(
        return_value=WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            current_task="Build auth",
        ),
    )
    store.delete = AsyncMock()
    store.exceeds_threshold = AsyncMock(return_value=False)
    return store


@pytest.fixture
def mock_module_store():
    store = MagicMock()
    store.insert = AsyncMock()
    store.insert_batch = AsyncMock()
    store.get_by_type = AsyncMock(return_value=[])
    store.get_unsynced = AsyncMock(return_value=[])
    store.mark_synced = AsyncMock()
    store.search_fulltext = AsyncMock(return_value=[])
    return store


@pytest.fixture
def mock_semantic_store():
    store = MagicMock()
    store.search = AsyncMock(return_value=[])
    store.ensure_collection = AsyncMock()
    return store


@pytest.fixture
def mock_compressor():
    comp = MagicMock()
    comp.compress = AsyncMock()
    comp.apply = MagicMock()
    return comp


@pytest.fixture
def mock_promoter():
    prom = MagicMock()
    prom.promote = MagicMock(return_value=[])
    return prom


@pytest.fixture
def mock_doc_syncer():
    ds = MagicMock()
    ds.sync = MagicMock(return_value=[])
    return ds


@pytest.fixture
def manager(
    mock_working_store,
    mock_module_store,
    mock_semantic_store,
    mock_compressor,
    mock_promoter,
    mock_doc_syncer,
    team_id,
    tournament_id,
):
    return MemoryManager(
        team_id=team_id,
        tournament_id=tournament_id,
        working_store=mock_working_store,
        module_store=mock_module_store,
        semantic_store=mock_semantic_store,
        compressor=mock_compressor,
        promoter=mock_promoter,
        doc_syncer=mock_doc_syncer,
    )


class TestMemoryManagerRecall:
    """Tests for MemoryManager.recall()."""

    @pytest.mark.asyncio
    async def test_recall_returns_memory_context(self, manager, agent_id) -> None:
        """recall() should return a MemoryContext with all 3 layers."""
        ctx = await manager.recall(agent_id, AgentRole.BUILDER, "auth login")
        assert isinstance(ctx, MemoryContext)
        assert ctx.working_state is not None

    @pytest.mark.asyncio
    async def test_recall_reads_all_3_layers(
        self,
        manager,
        mock_working_store,
        mock_module_store,
        mock_semantic_store,
        agent_id,
    ) -> None:
        """recall() should query L1, L2, and L3."""
        await manager.recall(agent_id, AgentRole.BUILDER, "auth")
        mock_working_store.load.assert_called_once()
        mock_module_store.search_fulltext.assert_called_once()
        mock_semantic_store.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_recall_triggers_overflow_when_exceeded(
        self,
        manager,
        mock_working_store,
        mock_compressor,
        agent_id,
    ) -> None:
        """recall() should trigger overflow handler when L1 exceeds threshold."""
        mock_working_store.exceeds_threshold = AsyncMock(return_value=True)
        mock_compressor.compress = AsyncMock(
            return_value=MagicMock(
                summary="compressed",
                preserved_decisions=[],
                dropped_count=5,
            ),
        )
        mock_compressor.apply = MagicMock(
            return_value=WorkingState(
                agent_id=agent_id,
                team_id=manager._team_id,
                role=AgentRole.BUILDER,
                current_phase=TournamentPhase.BUILD,
                context_summary="compressed",
            ),
        )
        await manager.recall(agent_id, AgentRole.BUILDER, "query")
        mock_compressor.compress.assert_called_once()


class TestMemoryManagerRecord:
    """Tests for MemoryManager.record()."""

    @pytest.mark.asyncio
    async def test_record_updates_l1(self, manager, mock_working_store, agent_id) -> None:
        """record() should update working state in Redis."""
        await manager.record(
            agent_id,
            AgentRole.BUILDER,
            task="Build auth endpoints",
            file_touched="src/auth.py",
        )
        mock_working_store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_with_decision_updates_decisions(
        self,
        manager,
        mock_working_store,
        agent_id,
    ) -> None:
        """record() with decision should append to recent_decisions."""
        await manager.record(
            agent_id,
            AgentRole.BUILDER,
            decision="Chose bcrypt for password hashing",
        )
        mock_working_store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_with_module_records_inserts_to_l2(
        self,
        manager,
        mock_module_store,
        agent_id,
        team_id,
        tournament_id,
    ) -> None:
        """record() with module_records should insert to L2."""
        records = [
            ModuleRecord(
                team_id=team_id,
                tournament_id=tournament_id,
                record_type=RecordType.ADR,
                module_name="auth",
                title="Test ADR",
                content="Content.",
            ),
        ]
        await manager.record(agent_id, AgentRole.BUILDER, module_records=records)
        mock_module_store.insert_batch.assert_called_once()


class TestMemoryManagerLifecycle:
    """Tests for initialize/teardown."""

    @pytest.mark.asyncio
    async def test_initialize_creates_l1(self, manager, mock_working_store, agent_id) -> None:
        """initialize() should create L1 state."""
        await manager.initialize(agent_id, AgentRole.BUILDER)
        mock_working_store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_teardown_deletes_l1(self, manager, mock_working_store, agent_id) -> None:
        """teardown() should delete L1 state."""
        await manager.teardown(agent_id, AgentRole.BUILDER)
        mock_working_store.delete.assert_called_once()
