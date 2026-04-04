"""Unit tests for MemoryManager behavior and resilience."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from packages.memory.src.manager import MemoryManager
from packages.memory.src.working.store import WorkingMemoryStore
from packages.shared.src.types.models import AgentRole


class _FakeRedis:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        _ = ex
        self._data[key] = value


@pytest.mark.asyncio
async def test_recall_empty_state_returns_stable_payload() -> None:
    client = _FakeRedis()
    store = WorkingMemoryStore(client, key_prefix="test:mm:empty")  # type: ignore[arg-type]
    manager = MemoryManager(store)

    out = await manager.recall(uuid4(), AgentRole.ARCHITECT, "what am I doing?")
    assert out["role"] == AgentRole.ARCHITECT.value
    assert out["l1"] == {}
    assert out["l2"] == []
    assert out["l3"] == []


@pytest.mark.asyncio
async def test_record_persists_fields_for_followup_recall() -> None:
    client = _FakeRedis()
    store = WorkingMemoryStore(client, key_prefix="test:mm:record")  # type: ignore[arg-type]
    manager = MemoryManager(store)
    agent_id = uuid4()

    await manager.record(
        agent_id,
        AgentRole.BUILDER,
        task="Implement websocket manager",
        decision="Use Redis streams for delivery",
        notes=["need retry policy"],
    )
    out = await manager.recall(agent_id, AgentRole.BUILDER, "resume")
    l1 = out["l1"]
    assert l1["last_task"] == "Implement websocket manager"
    assert l1["last_decision"] == "Use Redis streams for delivery"
    assert l1["notes"] == ["need retry policy"]
    assert isinstance(l1.get("recent_events", []), list)
    assert len(l1.get("recent_events", [])) == 1


class _FailingWorkingStore:
    async def get_state(self, agent_id: Any) -> dict[str, Any]:
        raise RuntimeError("boom")

    async def upsert_state(self, agent_id: Any, patch: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("boom")

    async def append_event(
        self,
        agent_id: Any,
        event: dict[str, Any],
        *,
        quality_score: float | None = None,
    ) -> dict[str, Any]:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_manager_degrades_gracefully_on_store_errors() -> None:
    manager = MemoryManager(_FailingWorkingStore())
    agent_id = uuid4()

    recall_out = await manager.recall(agent_id, AgentRole.TESTER, "continue")
    assert recall_out["l1"] == {}

    # Should not raise even when write path fails.
    await manager.record(agent_id, AgentRole.TESTER, task="run tests")


@pytest.mark.asyncio
async def test_manager_uses_module_store_for_l2() -> None:
    client = _FakeRedis()
    store = WorkingMemoryStore(client, key_prefix="test:mm:l2")  # type: ignore[arg-type]
    module_store = AsyncMock()
    module_store.search = AsyncMock(return_value=[{"task": "checkpoint"}])
    module_store.record = AsyncMock(return_value=None)
    manager = MemoryManager(store, module_store=module_store)
    agent_id = uuid4()
    team_id = uuid4()

    await manager.record(
        agent_id,
        AgentRole.ARCHITECT,
        task="Design durable state",
        decision="Use runtime_state",
        metadata={"team_id": str(team_id), "module_name": "core.orchestrator"},
    )
    out = await manager.recall(agent_id, AgentRole.ARCHITECT, "durable")

    assert out["l2"] == [{"task": "checkpoint"}]
    module_store.record.assert_awaited_once()
    module_store.search.assert_awaited_once()
