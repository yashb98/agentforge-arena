"""L1 working memory backed by Redis JSON payloads."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uuid import UUID

    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class WorkingMemoryStore:
    """Per-agent short-term memory with TTL for crash/restart recovery."""

    def __init__(
        self,
        redis_client: Redis,
        *,
        key_prefix: str = "memory:l1",
        ttl_seconds: int = 6 * 60 * 60,
        max_events: int = 50,
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds
        self._max_events = max_events

    def _key(self, agent_id: UUID) -> str:
        return f"{self._key_prefix}:{agent_id}"

    async def get_state(self, agent_id: UUID) -> dict[str, Any]:
        """Read current L1 state for an agent, defaulting to empty."""
        raw = await self._redis.get(self._key(agent_id))
        if raw is None:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid working-memory JSON for agent %s", agent_id)
            return {}
        return data if isinstance(data, dict) else {}

    async def upsert_state(self, agent_id: UUID, patch: dict[str, Any]) -> dict[str, Any]:
        """Merge patch into existing state and refresh TTL."""
        current = await self.get_state(agent_id)
        current.update(patch)
        await self._redis.set(
            self._key(agent_id),
            json.dumps(current),
            ex=self._ttl_seconds,
        )
        return current

    async def append_event(
        self,
        agent_id: UUID,
        event: dict[str, Any],
        *,
        quality_score: float | None = None,
    ) -> dict[str, Any]:
        """
        Append a timestamped event into bounded recent history.

        When over ``max_events``, evicts **lowest quality** first; ties break on
        **oldest** sequence number (LRU among equal-quality items).
        """
        current = await self.get_state(agent_id)
        events_raw = current.get("recent_events", [])
        events: list[dict[str, Any]] = [e for e in events_raw if isinstance(e, dict)]

        seq = int(current.get("_event_seq", 0)) + 1
        current["_event_seq"] = seq

        q = quality_score
        if q is None:
            raw_q = event.get("quality_score")
            if isinstance(raw_q, (int, float)):
                q = float(raw_q)
            else:
                q = 0.5
        q = max(0.0, min(1.0, float(q)))

        payload = {k: v for k, v in event.items() if k != "quality_score"}
        wrapped: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "_seq": seq,
            "_quality": q,
            **payload,
        }
        events.append(wrapped)

        while len(events) > self._max_events:
            idx_remove = min(
                range(len(events)),
                key=lambda i: (
                    float(events[i].get("_quality", 0.5)),
                    int(events[i].get("_seq", i)),
                ),
            )
            del events[idx_remove]

        current["recent_events"] = events
        await self._redis.set(
            self._key(agent_id),
            json.dumps(current),
            ex=self._ttl_seconds,
        )
        return current

    async def clear_state(self, agent_id: UUID) -> None:
        """Delete L1 memory payload for an agent."""
        await self._redis.delete(self._key(agent_id))
