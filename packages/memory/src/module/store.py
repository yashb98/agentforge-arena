"""L2 module memory store backed by PostgreSQL records."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.memory.src.module.hybrid_query import sanitize_fulltext_query
from packages.memory.src.module.rrf import reciprocal_rank_fusion
from packages.shared.src.db.base import get_session
from packages.shared.src.db.models import ModuleMemoryRecordDB

SessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]

_EXPECTED_EMB_DIM = 1536


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

    async def search_hybrid(
        self,
        *,
        team_id: UUID,
        query: str,
        limit: int = 10,
        module_name: str | None = None,
        query_embedding: list[float] | None = None,
        rrf_k: int = 60,
    ) -> list[ModuleMemoryRecordDB]:
        """
        Hybrid retrieval: PostgreSQL full-text (``tsvector``) + lexical ``ILIKE``,
        merged with RRF. Optionally adds a pgvector ordering branch when
        ``query_embedding`` is length *1536* and rows store embeddings.
        """
        safe = sanitize_fulltext_query(query) or ""
        fts_ids: list[UUID] = []
        like_ids: list[UUID] = []
        vec_ids: list[UUID] = []

        concat = func.concat(
            func.coalesce(ModuleMemoryRecordDB.task, ""),
            " ",
            func.coalesce(ModuleMemoryRecordDB.decision, ""),
        )
        tsv = func.to_tsvector("english", concat)

        async with self._session_provider() as session:
            if safe:
                tsq = func.plainto_tsquery("english", safe)
                stmt_ft = (
                    select(ModuleMemoryRecordDB.id)
                    .where(ModuleMemoryRecordDB.team_id == team_id)
                    .where(tsv.op("@@")(tsq))
                    .order_by(func.ts_rank_cd(tsv, tsq).desc())
                    .limit(max(limit * 3, 20))
                )
                if module_name is not None:
                    stmt_ft = stmt_ft.where(ModuleMemoryRecordDB.module_name == module_name)
                res_ft = await session.execute(stmt_ft)
                fts_ids = list(res_ft.scalars().all())

            stmt_like = (
                select(ModuleMemoryRecordDB.id)
                .where(ModuleMemoryRecordDB.team_id == team_id)
                .where(
                    or_(
                        ModuleMemoryRecordDB.task.ilike(f"%{query}%"),
                        ModuleMemoryRecordDB.decision.ilike(f"%{query}%"),
                    )
                )
                .order_by(desc(ModuleMemoryRecordDB.created_at))
                .limit(max(limit * 3, 20))
            )
            if module_name is not None:
                stmt_like = stmt_like.where(ModuleMemoryRecordDB.module_name == module_name)
            res_like = await session.execute(stmt_like)
            like_ids = list(res_like.scalars().all())

            if (
                query_embedding is not None
                and len(query_embedding) == _EXPECTED_EMB_DIM
            ):
                emb_lit = "[" + ",".join(str(float(x)) for x in query_embedding) + "]"
                sql_vec = text(
                    "SELECT id FROM module_memory_records WHERE team_id = CAST(:tid AS uuid) "
                    "AND embedding IS NOT NULL "
                    "ORDER BY embedding <=> CAST(:emb AS vector(1536)) "
                    "LIMIT :lim"
                )
                try:
                    res_v = await session.execute(
                        sql_vec,
                        {"tid": str(team_id), "emb": emb_lit, "lim": max(limit * 3, 20)},
                    )
                    vec_ids = [r[0] for r in res_v.fetchall()]
                except Exception:
                    vec_ids = []

            ranked = reciprocal_rank_fusion(
                [fts_ids, like_ids, vec_ids] if vec_ids else [fts_ids, like_ids],
                k=rrf_k,
                limit=limit,
            )
            if not ranked:
                return []

            id_order = [rid for rid, _ in ranked]
            stmt_rows = select(ModuleMemoryRecordDB).where(
                ModuleMemoryRecordDB.id.in_(id_order)
            )
            res_rows = await session.execute(stmt_rows)
            by_id = {row.id: row for row in res_rows.scalars().all()}
            return [by_id[i] for i in id_order if i in by_id]
