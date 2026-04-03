"""L2 module memory store backed by PostgreSQL records."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.src.db.base import get_session
from packages.shared.src.db.models import ModuleMemoryRecordDB

if TYPE_CHECKING:
    from uuid import UUID

SessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class ModuleMemoryStore:
    """Durable team/module memory used for multi-hour to multi-day context."""

    def __init__(self, session_provider: SessionProvider = get_session) -> None:
        self._session_provider = session_provider

    async def record(
        self,
        *,
        team_id: UUID,
        module_name: str,
        task: str | None = None,
        decision: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModuleMemoryRecordDB:
        """Persist one durable memory entry."""
        payload = metadata if metadata is not None else {}
        entry = ModuleMemoryRecordDB(
            team_id=team_id,
            module_name=module_name,
            task=task or "",
            decision=decision or "",
            metadata_json=payload,
        )
        async with self._session_provider() as session:
            session.add(entry)
            await session.flush()
            return entry

    async def search(
        self,
        *,
        team_id: UUID,
        query: str,
        limit: int = 10,
        module_name: str | None = None,
    ) -> list[ModuleMemoryRecordDB]:
        """Lexical fallback search over task/decision text."""
        stmt = (
            select(ModuleMemoryRecordDB)
            .where(ModuleMemoryRecordDB.team_id == team_id)
            .where(
                or_(
                    ModuleMemoryRecordDB.task.ilike(f"%{query}%"),
                    ModuleMemoryRecordDB.decision.ilike(f"%{query}%"),
                )
            )
            .order_by(desc(ModuleMemoryRecordDB.created_at))
            .limit(limit)
        )
        if module_name is not None:
            stmt = stmt.where(ModuleMemoryRecordDB.module_name == module_name)
        async with self._session_provider() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())
