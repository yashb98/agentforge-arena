"""Hybrid search (FTS + ILIKE + RRF) on module memory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from packages.memory.src.module.store import ModuleMemoryStore


@pytest.mark.asyncio
async def test_search_hybrid_merges_rankings() -> None:
    u1, u2, u3 = uuid4(), uuid4(), uuid4()
    team_id = uuid4()

    # FTS ids [u1, u2]; ILIKE [u2, u3]; fetch rows by fused order
    fts_result = MagicMock()
    fts_result.scalars.return_value.all.return_value = [u1, u2]
    like_result = MagicMock()
    like_result.scalars.return_value.all.return_value = [u2, u3]

    row_map = {
        u1: SimpleNamespace(id=u1, task="alpha"),
        u2: SimpleNamespace(id=u2, task="beta"),
        u3: SimpleNamespace(id=u3, task="gamma"),
    }
    final_rows = MagicMock()
    final_rows.scalars.return_value.all.return_value = [row_map[u2], row_map[u1], row_map[u3]]

    session = MagicMock()
    session.execute = AsyncMock(side_effect=[fts_result, like_result, final_rows])

    @asynccontextmanager
    async def provider() -> MagicMock:
        yield session

    store = ModuleMemoryStore(session_provider=provider)
    rows = await store.search_hybrid(team_id=team_id, query="beta token", limit=5)

    assert [r.id for r in rows] == [u2, u1, u3]
    assert session.execute.await_count == 3
