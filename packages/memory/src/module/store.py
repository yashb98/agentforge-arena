"""L2 Module Memory Store — PostgreSQL + pgvector structured records."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.module.queries import (
    select_by_module,
    select_by_type,
    select_fulltext,
    select_unsynced,
    update_synced,
)
from packages.shared.src.db.base import Base

logger = logging.getLogger(__name__)


class ModuleMemoryDB(Base):
    """SQLAlchemy ORM model for module_memory table."""

    __tablename__ = "module_memory"

    team_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    tournament_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    record_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    module_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # type: ignore[type-arg]
    agent_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    agent_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    synced_to_docs: Mapped[bool] = mapped_column(Boolean, default=False)
    ts_vector: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )  # Will be populated by trigger/manual update
    embedding: Mapped[Any] = mapped_column(Vector(384), nullable=True)  # type: ignore[misc]  # REASON: pgvector type has no stub


# Type alias for session factory
SessionFactory = Callable[[], "asynccontextmanager[AsyncGenerator[AsyncSession, None]]"]


class ModuleMemoryStore:
    """CRUD operations for L2 module memory in PostgreSQL."""

    def __init__(
        self,
        session_factory: Any,  # REASON: generic callable returning async context manager
        team_id: UUID,
        tournament_id: UUID,
    ) -> None:
        self._session_factory = session_factory
        self._team_id = team_id
        self._tournament_id = tournament_id

    def _to_db(self, record: ModuleRecord) -> ModuleMemoryDB:
        """Convert Pydantic model to SQLAlchemy ORM instance."""
        return ModuleMemoryDB(
            id=record.id,
            team_id=record.team_id,
            tournament_id=record.tournament_id,
            record_type=record.record_type.value,
            module_name=record.module_name,
            file_path=record.file_path,
            title=record.title,
            content=record.content,
            metadata_json=record.metadata,
            agent_id=record.agent_id,
            agent_role=record.agent_role.value if record.agent_role else None,
            synced_to_docs=record.synced_to_docs,
        )

    def _from_db(self, row: ModuleMemoryDB) -> ModuleRecord:
        """Convert SQLAlchemy ORM instance to Pydantic model."""
        from packages.shared.src.types.models import AgentRole

        return ModuleRecord(
            id=row.id,
            team_id=row.team_id,
            tournament_id=row.tournament_id,
            record_type=RecordType(row.record_type),
            module_name=row.module_name,
            file_path=row.file_path,
            title=row.title,
            content=row.content,
            metadata=row.metadata_json,
            agent_id=row.agent_id,
            agent_role=AgentRole(row.agent_role) if row.agent_role else None,
            synced_to_docs=row.synced_to_docs,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def insert(self, record: ModuleRecord) -> None:
        """Insert a single record."""
        async with self._session_factory() as session:
            session.add(self._to_db(record))
            await session.flush()

    async def insert_batch(self, records: list[ModuleRecord]) -> None:
        """Insert multiple records in one transaction."""
        async with self._session_factory() as session:
            for record in records:
                session.add(self._to_db(record))
            await session.flush()

    async def get_by_type(
        self, record_type: RecordType, *, limit: int = 50
    ) -> list[ModuleRecord]:
        """Get records by type for this team."""
        async with self._session_factory() as session:
            stmt = select_by_type(self._team_id, record_type, limit=limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._from_db(row) for row in rows]

    async def get_by_module(
        self, module_name: str, *, limit: int = 20
    ) -> list[ModuleRecord]:
        """Get records for a specific module."""
        async with self._session_factory() as session:
            stmt = select_by_module(self._team_id, module_name, limit=limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._from_db(row) for row in rows]

    async def get_unsynced(self) -> list[ModuleRecord]:
        """Get records not yet synced to docs."""
        async with self._session_factory() as session:
            stmt = select_unsynced(self._team_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._from_db(row) for row in rows]

    async def mark_synced(self, record_ids: list[UUID]) -> None:
        """Mark records as synced to docs."""
        if not record_ids:
            return
        async with self._session_factory() as session:
            stmt = update_synced(record_ids)
            await session.execute(stmt)

    async def search_fulltext(self, query: str, *, limit: int = 10) -> list[ModuleRecord]:
        """Full-text search across module records."""
        async with self._session_factory() as session:
            stmt = select_fulltext(self._team_id, query, limit=limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._from_db(row) for row in rows]
