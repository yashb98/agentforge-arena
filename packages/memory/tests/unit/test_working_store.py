"""Tests for L1 WorkingMemoryStore (Redis)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import orjson
import pytest

from packages.memory.src.working.models import WorkingState
from packages.memory.src.working.store import WorkingMemoryStore
from packages.shared.src.types.models import AgentRole, TournamentPhase


@pytest.fixture()
def store(mock_redis, team_id) -> WorkingMemoryStore:
    return WorkingMemoryStore(redis=mock_redis, team_id=team_id)


@pytest.fixture()
def sample_state(agent_id, team_id) -> WorkingState:
    return WorkingState(
        agent_id=agent_id,
        team_id=team_id,
        role=AgentRole.BUILDER,
        current_phase=TournamentPhase.BUILD,
        current_task="Build auth API",
    )


class TestWorkingMemoryStore:
    """Tests for Redis-backed working memory."""

    def test_key_format(self, store, agent_id) -> None:
        """Redis key should follow working:{team_id}:{role} pattern."""
        key = store._state_key(AgentRole.BUILDER)
        assert "working:" in key
        assert "builder" in key

    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(
        self, store, mock_redis, agent_id, sample_state
    ) -> None:
        """save() then load() should return equivalent state."""
        # Configure mock to return what was saved
        saved_data = {}

        async def capture_set(key, value, **kwargs):
            saved_data["key"] = key
            saved_data["value"] = value

        mock_redis.set = AsyncMock(side_effect=capture_set)
        mock_redis.get = AsyncMock(
            side_effect=lambda key: saved_data.get("value")
        )

        await store.save(sample_state)
        mock_redis.set.assert_called_once()

        result = await store.load(AgentRole.BUILDER)
        assert result is not None
        assert result.current_task == "Build auth API"

    @pytest.mark.asyncio
    async def test_load_nonexistent_returns_none(self, store, mock_redis) -> None:
        """load() for non-existent agent should return None."""
        mock_redis.get = AsyncMock(return_value=None)
        result = await store.load(AgentRole.BUILDER)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_removes_key(self, store, mock_redis) -> None:
        """delete() should remove the Redis key."""
        await store.delete(AgentRole.BUILDER)
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_sets_ttl(self, store, mock_redis, sample_state) -> None:
        """save() should set TTL on the key."""
        await store.save(sample_state, ttl_seconds=3600)
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_exceeds_threshold_true_when_over(
        self, store, mock_redis, sample_state
    ) -> None:
        """exceeds_threshold() should return True when tokens > threshold."""
        # Create a state with a lot of content
        big_state = sample_state.model_copy(
            update={"context_summary": "x" * 10000}
        )
        data = big_state.model_dump_json().encode()
        mock_redis.get = AsyncMock(return_value=data)
        result = await store.exceeds_threshold(AgentRole.BUILDER, threshold=2000)
        assert result is True

    @pytest.mark.asyncio
    async def test_exceeds_threshold_false_when_under(
        self, store, mock_redis, sample_state
    ) -> None:
        """exceeds_threshold() should return False when tokens < threshold."""
        data = sample_state.model_dump_json().encode()
        mock_redis.get = AsyncMock(return_value=data)
        result = await store.exceeds_threshold(AgentRole.BUILDER, threshold=2000)
        assert result is False
