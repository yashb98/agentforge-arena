"""Unit tests for Redis-backed L1 working memory."""

from __future__ import annotations

from uuid import uuid4

import pytest

from packages.memory.src.working.store import WorkingMemoryStore


class _FakeRedis:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        _ = ex
        self._data[key] = value

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)


@pytest.fixture()
async def store() -> WorkingMemoryStore:
    client = _FakeRedis()
    return WorkingMemoryStore(
        client,  # type: ignore[arg-type]
        key_prefix="test:memory:l1",
        ttl_seconds=120,
        max_events=3,
    )


@pytest.mark.asyncio
async def test_upsert_and_get_state(store: WorkingMemoryStore) -> None:
    agent_id = uuid4()
    await store.upsert_state(agent_id, {"last_task": "implement auth"})
    state = await store.get_state(agent_id)
    assert state["last_task"] == "implement auth"


@pytest.mark.asyncio
async def test_append_event_is_bounded(store: WorkingMemoryStore) -> None:
    agent_id = uuid4()
    for idx in range(5):
        await store.append_event(agent_id, {"event": "step", "index": idx})

    state = await store.get_state(agent_id)
    events = state["recent_events"]
    assert isinstance(events, list)
    assert len(events) == 3
    assert events[0]["index"] == 2
    assert events[-1]["index"] == 4


@pytest.mark.asyncio
async def test_clear_state_removes_payload(store: WorkingMemoryStore) -> None:
    agent_id = uuid4()
    await store.upsert_state(agent_id, {"notes": ["a", "b"]})
    await store.clear_state(agent_id)
    state = await store.get_state(agent_id)
    assert state == {}
