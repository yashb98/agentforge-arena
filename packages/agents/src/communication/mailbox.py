"""
AgentForge Arena — Redis Agent Mailbox

Production-grade agent communication via Redis lists.
Replaces JSON file-based mailboxes (which have file locking issues — see Gotcha G010).

Each agent has an inbox (Redis list). Messages are atomic (LPUSH/BRPOP).
"""

from __future__ import annotations

import logging
from uuid import UUID

import orjson
import redis.asyncio as aioredis

from packages.shared.src.types.models import AgentMessage, AgentRole

logger = logging.getLogger(__name__)


class RedisMailbox:
    """Redis-based agent mailbox for reliable inter-agent communication."""

    KEY_PREFIX = "mailbox"

    def __init__(self, redis: aioredis.Redis, team_id: UUID) -> None:
        self._redis = redis
        self._team_id = team_id

    def _inbox_key(self, role: AgentRole) -> str:
        """Redis key for an agent's inbox."""
        return f"{self.KEY_PREFIX}:{self._team_id}:{role.value}"

    async def send(self, message: AgentMessage) -> None:
        """Send a message to one or all agents."""
        data = orjson.dumps(message.model_dump(mode="json"))

        if message.to_agent is not None:
            # Direct message
            key = self._inbox_key(message.to_agent)
            await self._redis.lpush(key, data)
            logger.debug(
                "Message sent: %s → %s (%s)",
                message.from_agent.value,
                message.to_agent.value,
                message.message_type.value,
            )
        else:
            # Broadcast to all agents except sender
            for role in AgentRole:
                if role != message.from_agent:
                    key = self._inbox_key(role)
                    await self._redis.lpush(key, data)
            logger.debug(
                "Broadcast from %s: %s",
                message.from_agent.value,
                message.message_type.value,
            )

    async def receive(
        self, role: AgentRole, *, timeout: float = 5.0
    ) -> AgentMessage | None:
        """Receive the next message from an agent's inbox (blocking)."""
        key = self._inbox_key(role)
        result = await self._redis.brpop(key, timeout=timeout)

        if result is None:
            return None

        _key, data = result
        msg_dict = orjson.loads(data)
        return AgentMessage.model_validate(msg_dict, strict=False)

    async def receive_all(self, role: AgentRole) -> list[AgentMessage]:
        """Receive all pending messages (non-blocking)."""
        key = self._inbox_key(role)
        messages: list[AgentMessage] = []

        while True:
            data = await self._redis.rpop(key)
            if data is None:
                break
            msg_dict = orjson.loads(data)
            messages.append(AgentMessage.model_validate(msg_dict, strict=False))

        return messages

    async def peek(self, role: AgentRole, count: int = 10) -> list[AgentMessage]:
        """Peek at messages without removing them."""
        key = self._inbox_key(role)
        items = await self._redis.lrange(key, -count, -1)

        messages = []
        for data in reversed(items):
            msg_dict = orjson.loads(data)
            messages.append(AgentMessage.model_validate(msg_dict, strict=False))

        return messages

    async def inbox_size(self, role: AgentRole) -> int:
        """Get the number of messages in an agent's inbox."""
        key = self._inbox_key(role)
        return await self._redis.llen(key)

    async def clear_inbox(self, role: AgentRole) -> int:
        """Clear all messages from an agent's inbox. Returns count cleared."""
        key = self._inbox_key(role)
        count = await self._redis.llen(key)
        await self._redis.delete(key)
        return count

    async def clear_team(self) -> None:
        """Clear all mailboxes for this team."""
        for role in AgentRole:
            await self.clear_inbox(role)
