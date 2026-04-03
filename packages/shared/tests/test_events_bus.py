"""
Tests for Redis Streams EventBus (mocked redis client).
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import redis.asyncio as aioredis

from packages.shared.src.events.bus import EventBus
from packages.shared.src.types.models import ArenaEvent


@pytest.fixture()
def redis_client() -> AsyncMock:
    r = AsyncMock(spec=aioredis.Redis)
    r.xadd = AsyncMock(return_value=b"1-0")
    r.publish = AsyncMock(return_value=1)
    r.xack = AsyncMock(return_value=1)
    r.xgroup_create = AsyncMock(return_value=True)
    r.xreadgroup = AsyncMock(return_value=[])
    r.xrange = AsyncMock(return_value=[])
    r.xinfo_stream = AsyncMock(
        return_value={"length": 0, "first-entry": None, "last-entry": None, "groups": 0}
    )
    return r


@pytest.mark.asyncio
async def test_publish_serializes_event_and_returns_id(redis_client: AsyncMock) -> None:
    bus = EventBus(redis_client)
    tid = uuid4()
    eid = await bus.publish(
        "tournament.started",
        payload={"phase": "prep"},
        source="test",
        tournament_id=tid,
    )
    assert eid == "1-0"
    redis_client.xadd.assert_awaited_once()
    redis_client.publish.assert_awaited_once()
    call_kw = redis_client.xadd.await_args.kwargs
    assert call_kw["maxlen"] == EventBus.MAX_STREAM_LEN


@pytest.mark.asyncio
async def test_subscribe_registers_handler(redis_client: AsyncMock) -> None:
    bus = EventBus(redis_client)

    @bus.subscribe("tournament.*")
    async def handler(_event: ArenaEvent) -> None:
        return None

    assert "tournament.*" in bus._handlers
    assert handler in bus._handlers["tournament.*"]


@pytest.mark.asyncio
async def test_dispatch_invokes_matching_handler_and_xacks(
    redis_client: AsyncMock,
) -> None:
    bus = EventBus(redis_client)
    seen: list[str] = []

    @bus.subscribe("agent.*")
    async def h(ev: ArenaEvent) -> None:
        seen.append(ev.event_type)

    event = ArenaEvent(
        event_type="agent.task.done",
        source="x",
        payload={},
        correlation_id=uuid4(),
    )
    raw = event.model_dump_json().encode()
    bus._consumer_group = "test-group"
    await bus._dispatch(b"99-0", {b"event": raw})

    assert seen == ["agent.task.done"]
    redis_client.xack.assert_awaited()


@pytest.mark.asyncio
async def test_dispatch_no_handler_skips_xack(redis_client: AsyncMock) -> None:
    bus = EventBus(redis_client)
    event = ArenaEvent(
        event_type="other.event",
        source="x",
        payload={},
        correlation_id=uuid4(),
    )
    await bus._dispatch(b"1-0", {b"event": event.model_dump_json().encode()})
    redis_client.xack.assert_not_awaited()


@pytest.mark.asyncio
async def test_replay_applies_filters(redis_client: AsyncMock) -> None:
    tid = uuid4()
    ev_match = ArenaEvent(
        event_type="tournament.phase",
        source="s",
        tournament_id=tid,
        payload={},
        correlation_id=uuid4(),
    )
    ev_other = ArenaEvent(
        event_type="other.x",
        source="s",
        tournament_id=tid,
        payload={},
        correlation_id=uuid4(),
    )
    redis_client.xrange = AsyncMock(
        return_value=[
            (b"1-0", {b"event": ev_match.model_dump_json().encode()}),
            (b"2-0", {b"event": ev_other.model_dump_json().encode()}),
        ]
    )
    bus = EventBus(redis_client)
    out = await bus.replay(event_type_filter="tournament.*", tournament_id=str(tid))
    assert len(out) == 1
    assert out[0].event_type == "tournament.phase"


@pytest.mark.asyncio
async def test_replay_skips_wrong_tournament_id(redis_client: AsyncMock) -> None:
    tid = uuid4()
    ev = ArenaEvent(
        event_type="x.y",
        source="s",
        tournament_id=tid,
        payload={},
        correlation_id=uuid4(),
    )
    redis_client.xrange = AsyncMock(
        return_value=[(b"1-0", {b"event": ev.model_dump_json().encode()})]
    )
    bus = EventBus(redis_client)
    out = await bus.replay(tournament_id=str(uuid4()))
    assert out == []


@pytest.mark.asyncio
async def test_stream_info_returns_subset(redis_client: AsyncMock) -> None:
    redis_client.xinfo_stream = AsyncMock(return_value={"length": 3, "groups": 1})
    bus = EventBus(redis_client)
    info = await bus.stream_info()
    assert info["length"] == 3
    assert info["groups"] == 1


@pytest.mark.asyncio
async def test_start_consuming_propagates_xgroup_error_when_not_busygroup(
    redis_client: AsyncMock,
) -> None:
    err = aioredis.ResponseError("ERR some other redis failure")
    redis_client.xgroup_create = AsyncMock(side_effect=err)
    bus = EventBus(redis_client)
    with pytest.raises(aioredis.ResponseError):
        await bus.start_consuming("g1", "c1", batch_size=1, block_ms=1)


@pytest.mark.asyncio
async def test_stop_sets_running_false(redis_client: AsyncMock) -> None:
    bus = EventBus(redis_client)
    bus._running = True
    await bus.stop()
    assert bus._running is False
