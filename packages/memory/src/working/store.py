"""L1 Working Memory Store — Redis Hash + JSON per-agent state."""

from __future__ import annotations

import logging
from uuid import UUID

import redis.asyncio as aioredis

from packages.memory.src.working.models import WorkingState
from packages.shared.src.types.models import AgentRole

logger = logging.getLogger(__name__)


class WorkingMemoryStore:
    """Per-agent working memory backed by Redis.

    Each agent gets a single Redis key containing its full WorkingState
    serialized as JSON. This is simpler than Hash + JSON split and sufficient
    since we always read/write the full state atomically.
    """

    KEY_PREFIX = "working"

    def __init__(self, redis: aioredis.Redis, team_id: UUID) -> None:
        self._redis = redis
        self._team_id = team_id

    def _state_key(self, role: AgentRole) -> str:
        """Redis key for an agent's working state."""
        return f"{self.KEY_PREFIX}:{self._team_id}:{role.value}"

    async def save(self, state: WorkingState, *, ttl_seconds: int | None = None) -> None:
        """Persist working state to Redis."""
        key = self._state_key(state.role)
        data = state.model_dump_json().encode()
        await self._redis.set(key, data)
        if ttl_seconds is not None:
            await self._redis.expire(key, ttl_seconds)
        logger.debug("Saved working state for %s (%d bytes)", state.role.value, len(data))

    async def load(self, role: AgentRole) -> WorkingState | None:
        """Load working state from Redis. Returns None if not found."""
        key = self._state_key(role)
        data = await self._redis.get(key)
        if data is None:
            return None
        return WorkingState.model_validate_json(data)

    async def delete(self, role: AgentRole) -> None:
        """Delete working state for an agent."""
        key = self._state_key(role)
        await self._redis.delete(key)
        logger.debug("Deleted working state for %s", role.value)

    async def exceeds_threshold(self, role: AgentRole, *, threshold: int = 2000) -> bool:
        """Check if working state exceeds the token threshold for compression."""
        key = self._state_key(role)
        data = await self._redis.get(key)
        if data is None:
            return False
        state = WorkingState.model_validate_json(data)
        return state.estimate_tokens() > threshold

    async def clear_team(self) -> None:
        """Delete all working memory keys for this team."""
        for role in AgentRole:
            await self.delete(role)
