"""Tests for L2 ModuleMemoryStore (PostgreSQL + pgvector)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.module.store import ModuleMemoryStore
from packages.shared.src.types.models import AgentRole


@pytest.fixture()
def mock_session():
    """Create a mock async SQLAlchemy session."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture()
def mock_session_factory(mock_session):
    """Create a mock session context manager factory."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def factory():
        yield mock_session

    return factory


@pytest.fixture()
def store(mock_session_factory, team_id, tournament_id) -> ModuleMemoryStore:
    return ModuleMemoryStore(
        session_factory=mock_session_factory,
        team_id=team_id,
        tournament_id=tournament_id,
    )


@pytest.fixture()
def sample_record(team_id, tournament_id) -> ModuleRecord:
    return ModuleRecord(
        team_id=team_id,
        tournament_id=tournament_id,
        record_type=RecordType.ADR,
        module_name="auth",
        title="Chose bcrypt",
        content="bcrypt for password hashing — simpler API.",
        agent_role=AgentRole.BUILDER,
    )


class TestModuleMemoryStore:
    """Tests for PostgreSQL-backed module memory."""

    @pytest.mark.asyncio
    async def test_insert_record(self, store, mock_session, sample_record) -> None:
        """insert() should add a record to the session."""
        await store.insert(sample_record)
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_insert_batch(self, store, mock_session, team_id, tournament_id) -> None:
        """insert_batch() should add multiple records."""
        records = [
            ModuleRecord(
                team_id=team_id,
                tournament_id=tournament_id,
                record_type=RecordType.GOTCHA,
                module_name="cache",
                title=f"Gotcha {i}",
                content=f"Content {i}",
            )
            for i in range(3)
        ]
        await store.insert_batch(records)
        assert mock_session.add.call_count == 3

    @pytest.mark.asyncio
    async def test_get_by_type(self, store, mock_session) -> None:
        """get_by_type() should query with correct record_type filter."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        mock_session.execute = AsyncMock(return_value=mock_result)

        results = await store.get_by_type(RecordType.ADR)
        assert isinstance(results, list)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_unsynced(self, store, mock_session) -> None:
        """get_unsynced() should return records where synced_to_docs=False."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        mock_session.execute = AsyncMock(return_value=mock_result)

        results = await store.get_unsynced()
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_mark_synced(self, store, mock_session) -> None:
        """mark_synced() should update synced_to_docs to True."""
        record_ids = [uuid4(), uuid4()]
        mock_session.execute = AsyncMock()
        await store.mark_synced(record_ids)
        mock_session.execute.assert_called_once()
