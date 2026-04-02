"""Hybrid SQL + vector query builders for L2 module memory."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, and_, func, select, update

from packages.memory.src.module.models import RecordType


def select_by_type(
    team_id: UUID,
    record_type: RecordType,
    *,
    limit: int = 50,
) -> Select:  # type: ignore[type-arg]
    """Build query to select records by type for a team."""
    from packages.memory.src.module.store import ModuleMemoryDB

    return (
        select(ModuleMemoryDB)
        .where(
            and_(
                ModuleMemoryDB.team_id == team_id,
                ModuleMemoryDB.record_type == record_type.value,
            )
        )
        .order_by(ModuleMemoryDB.created_at.desc())
        .limit(limit)
    )


def select_by_module(
    team_id: UUID,
    module_name: str,
    *,
    limit: int = 20,
) -> Select:  # type: ignore[type-arg]
    """Build query to select records for a specific module."""
    from packages.memory.src.module.store import ModuleMemoryDB

    return (
        select(ModuleMemoryDB)
        .where(
            and_(
                ModuleMemoryDB.team_id == team_id,
                ModuleMemoryDB.module_name == module_name,
            )
        )
        .order_by(ModuleMemoryDB.created_at.desc())
        .limit(limit)
    )


def select_unsynced(team_id: UUID) -> Select:  # type: ignore[type-arg]
    """Build query to select records not yet synced to docs."""
    from packages.memory.src.module.store import ModuleMemoryDB

    return (
        select(ModuleMemoryDB)
        .where(
            and_(
                ModuleMemoryDB.team_id == team_id,
                ModuleMemoryDB.synced_to_docs == False,  # noqa: E712
            )
        )
        .order_by(ModuleMemoryDB.created_at.asc())
    )


def update_synced(record_ids: list[UUID]) -> update:  # type: ignore[type-arg]
    """Build update statement to mark records as synced."""
    from packages.memory.src.module.store import ModuleMemoryDB

    return (
        update(ModuleMemoryDB)
        .where(ModuleMemoryDB.id.in_(record_ids))
        .values(synced_to_docs=True)
    )


def select_fulltext(team_id: UUID, query: str, *, limit: int = 10) -> Select:  # type: ignore[type-arg]
    """Build full-text search query using ts_vector."""
    from packages.memory.src.module.store import ModuleMemoryDB

    ts_query = func.plainto_tsquery("english", query)
    return (
        select(ModuleMemoryDB)
        .where(
            and_(
                ModuleMemoryDB.team_id == team_id,
                ModuleMemoryDB.ts_vector.op("@@")(ts_query),
            )
        )
        .order_by(func.ts_rank(ModuleMemoryDB.ts_vector, ts_query).desc())
        .limit(limit)
    )
