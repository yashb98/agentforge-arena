"""Tests for RedisMailbox with mocked Redis."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import orjson
import pytest

from packages.agents.src.communication.mailbox import RedisMailbox
from packages.shared.src.types.models import AgentMessage, AgentRole, MessageType


@pytest.fixture()
def redis_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture()
def team_id() -> object:
    return uuid4()


@pytest.fixture()
def mailbox(redis_client: AsyncMock, team_id: object) -> RedisMailbox:
    return RedisMailbox(redis_client, team_id)


def _msg(
    *,
    to_agent: AgentRole | None = AgentRole.BUILDER,
    from_agent: AgentRole = AgentRole.ARCHITECT,
) -> AgentMessage:
    return AgentMessage(
        from_agent=from_agent,
        to_agent=to_agent,
        message_type=MessageType.TASK_ASSIGNMENT,
        payload={"x": 1},
    )


@pytest.mark.asyncio
async def test_send_direct_lpushes_to_role_inbox(
    mailbox: RedisMailbox, redis_client: AsyncMock, team_id: object
) -> None:
    msg = _msg()
    await mailbox.send(msg)
    redis_client.lpush.assert_awaited_once()
    key = redis_client.lpush.await_args[0][0]
    assert f"{mailbox.KEY_PREFIX}:{team_id}:{AgentRole.BUILDER.value}" == key


@pytest.mark.asyncio
async def test_send_broadcast_skips_sender(
    mailbox: RedisMailbox, redis_client: AsyncMock
) -> None:
    msg = AgentMessage(
        from_agent=AgentRole.ARCHITECT,
        to_agent=None,
        message_type=MessageType.STATUS_UPDATE,
        payload={},
    )
    await mailbox.send(msg)
    assert redis_client.lpush.await_count == len(AgentRole) - 1


@pytest.mark.asyncio
async def test_receive_returns_none_on_timeout(
    mailbox: RedisMailbox, redis_client: AsyncMock
) -> None:
    redis_client.brpop = AsyncMock(return_value=None)
    out = await mailbox.receive(AgentRole.TESTER, timeout=0.1)
    assert out is None


@pytest.mark.asyncio
async def test_receive_parses_message(
    mailbox: RedisMailbox, redis_client: AsyncMock
) -> None:
    msg = _msg()
    data = orjson.dumps(msg.model_dump(mode="json"))
    redis_client.brpop = AsyncMock(return_value=(b"key", data))
    out = await mailbox.receive(AgentRole.BUILDER)
    assert out is not None
    assert out.message_type == MessageType.TASK_ASSIGNMENT


@pytest.mark.asyncio
async def test_receive_all_drains_list(
    mailbox: RedisMailbox, redis_client: AsyncMock
) -> None:
    msg = _msg()
    data = orjson.dumps(msg.model_dump(mode="json"))
    redis_client.rpop = AsyncMock(side_effect=[data, None])
    out = await mailbox.receive_all(AgentRole.BUILDER)
    assert len(out) == 1


@pytest.mark.asyncio
async def test_peek_returns_messages_newest_first_order(
    mailbox: RedisMailbox, redis_client: AsyncMock
) -> None:
    m1 = _msg()
    m2 = _msg()
    d1 = orjson.dumps(m1.model_dump(mode="json"))
    d2 = orjson.dumps(m2.model_dump(mode="json"))
    redis_client.lrange = AsyncMock(return_value=[d1, d2])
    out = await mailbox.peek(AgentRole.BUILDER, count=10)
    assert len(out) == 2


@pytest.mark.asyncio
async def test_inbox_size_and_clear(
    mailbox: RedisMailbox, redis_client: AsyncMock
) -> None:
    redis_client.llen = AsyncMock(return_value=3)
    assert await mailbox.inbox_size(AgentRole.CRITIC) == 3
    redis_client.delete = AsyncMock(return_value=1)
    cleared = await mailbox.clear_inbox(AgentRole.CRITIC)
    assert cleared == 3


@pytest.mark.asyncio
async def test_clear_team_clears_each_role(
    mailbox: RedisMailbox, redis_client: AsyncMock
) -> None:
    redis_client.llen = AsyncMock(return_value=0)
    redis_client.delete = AsyncMock(return_value=1)
    await mailbox.clear_team()
    assert redis_client.delete.await_count == len(AgentRole)
