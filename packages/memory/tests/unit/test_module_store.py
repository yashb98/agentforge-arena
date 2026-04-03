"""Unit tests for L2 ModuleMemoryStore."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from packages.memory.src.module.store import ModuleMemoryStore


def _session_provider(
    *,
    execute_result: Any | None = None,
) -> tuple[Any, ModuleMemoryStore]:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    if execute_result is None:
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=execute_result)

    @asynccontextmanager
    async def provider() -> Any:
        yield session

    return session, ModuleMemoryStore(session_provider=provider)


@pytest.mark.asyncio
async def test_record_adds_and_flushes_entry() -> None:
    session, store = _session_provider()
    team_id = uuid4()

    entry = await store.record(
        team_id=team_id,
        module_name="core.orchestrator",
        task="persist checkpoint",
        decision="store runtime_state in jsonb",
        metadata={"priority": "p0"},
    )

    session.add.assert_called_once()
    session.flush.assert_awaited_once()
    assert entry.team_id == team_id
    assert entry.module_name == "core.orchestrator"


@pytest.mark.asyncio
async def test_search_returns_scalar_rows() -> None:
    row_a = SimpleNamespace(task="task-a")
    row_b = SimpleNamespace(task="task-b")
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [row_a, row_b]
    session, store = _session_provider(execute_result=execute_result)

    rows = await store.search(team_id=uuid4(), query="task", limit=5)

    session.execute.assert_awaited_once()
    assert rows == [row_a, row_b]
