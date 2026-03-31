"""
AgentForge Arena — Event Bus (Redis Streams)

Persistent, replayable event bus for inter-service communication.
All state changes are published as events. Services subscribe via consumer groups.

Usage:
    bus = EventBus(redis_client)
    await bus.publish("tournament.phase.changed", payload={...})

    @bus.subscribe("tournament.*")
    async def handle(event: ArenaEvent):
        ...
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import orjson
import redis.asyncio as aioredis

from packages.shared.src.types.models import ArenaEvent

logger = logging.getLogger(__name__)

# Type alias for event handlers
EventHandler = Callable[[ArenaEvent], Awaitable[None]]


class EventBus:
    """Redis Streams-based event bus with consumer groups."""

    STREAM_KEY = "arena:events"
    MAX_STREAM_LEN = 100_000  # Trim stream to prevent unbounded growth

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._handlers: dict[str, list[EventHandler]] = {}
        self._consumer_group: str = ""
        self._consumer_name: str = ""
        self._running = False

    async def publish(
        self,
        event_type: str,
        *,
        payload: dict[str, Any] | None = None,
        source: str = "unknown",
        tournament_id: UUID | None = None,
        team_id: UUID | None = None,
        agent_id: UUID | None = None,
        correlation_id: UUID | None = None,
    ) -> str:
        """Publish an event to the stream. Returns the stream entry ID."""
        event = ArenaEvent(
            event_type=event_type,
            source=source,
            payload=payload or {},
            tournament_id=tournament_id,
            team_id=team_id,
            agent_id=agent_id,
            correlation_id=correlation_id or UUID(int=0),
        )

        data = orjson.dumps(event.model_dump(mode="json")).decode()
        entry_id: bytes = await self._redis.xadd(
            self.STREAM_KEY,
            {"event": data},
            maxlen=self.MAX_STREAM_LEN,
            approximate=True,
        )

        logger.debug("Published event %s: %s", event_type, entry_id.decode())

        # Also publish to Pub/Sub for real-time spectator streaming
        await self._redis.publish(
            f"arena:realtime:{event_type}",
            data,
        )

        return entry_id.decode()

    def subscribe(
        self, pattern: str
    ) -> Callable[[EventHandler], EventHandler]:
        """Decorator to register an event handler for a pattern.

        Supports glob patterns: 'tournament.*', 'agent.task.*', etc.
        """

        def decorator(func: EventHandler) -> EventHandler:
            if pattern not in self._handlers:
                self._handlers[pattern] = []
            self._handlers[pattern].append(func)
            logger.info("Registered handler %s for pattern %s", func.__name__, pattern)
            return func

        return decorator

    async def start_consuming(
        self,
        group: str,
        consumer: str,
        *,
        batch_size: int = 10,
        block_ms: int = 1000,
    ) -> None:
        """Start consuming events from the stream using a consumer group."""
        self._consumer_group = group
        self._consumer_name = consumer
        self._running = True

        # Create consumer group if it doesn't exist
        try:
            await self._redis.xgroup_create(
                self.STREAM_KEY, group, id="0", mkstream=True
            )
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        logger.info("Consumer %s/%s started on stream %s", group, consumer, self.STREAM_KEY)

        while self._running:
            try:
                entries = await self._redis.xreadgroup(
                    groupname=group,
                    consumername=consumer,
                    streams={self.STREAM_KEY: ">"},
                    count=batch_size,
                    block=block_ms,
                )

                if not entries:
                    continue

                for _stream, messages in entries:
                    for msg_id, msg_data in messages:
                        await self._dispatch(msg_id, msg_data)

            except asyncio.CancelledError:
                logger.info("Consumer %s/%s stopping", group, consumer)
                self._running = False
                break
            except Exception:
                logger.exception("Error in event consumer loop")
                await asyncio.sleep(1)

    async def _dispatch(self, msg_id: bytes, msg_data: dict[bytes, bytes]) -> None:
        """Dispatch an event to matching handlers."""
        try:
            raw = msg_data.get(b"event", b"{}")
            event = ArenaEvent.model_validate_json(raw)

            dispatched = False
            for pattern, handlers in self._handlers.items():
                if fnmatch.fnmatch(event.event_type, pattern):
                    for handler in handlers:
                        try:
                            await handler(event)
                            dispatched = True
                        except Exception:
                            logger.exception(
                                "Handler error for event %s: %s",
                                event.event_type,
                                handler.__name__,
                            )

            if dispatched:
                # Acknowledge the message
                await self._redis.xack(
                    self.STREAM_KEY, self._consumer_group, msg_id
                )

        except Exception:
            logger.exception("Failed to dispatch event %s", msg_id)

    async def stop(self) -> None:
        """Stop the consumer loop."""
        self._running = False

    async def replay(
        self,
        *,
        start: str = "0",
        end: str = "+",
        count: int = 1000,
        event_type_filter: str | None = None,
        tournament_id: str | None = None,
    ) -> list[ArenaEvent]:
        """Replay events from the stream for debugging or replay generation."""
        entries = await self._redis.xrange(self.STREAM_KEY, min=start, max=end, count=count)

        events = []
        for _entry_id, data in entries:
            raw = data.get(b"event", b"{}")
            event = ArenaEvent.model_validate_json(raw)

            if event_type_filter and not fnmatch.fnmatch(event.event_type, event_type_filter):
                continue
            if tournament_id and str(event.tournament_id) != tournament_id:
                continue

            events.append(event)

        return events

    async def stream_info(self) -> dict[str, Any]:
        """Get stream metadata for health checks."""
        info = await self._redis.xinfo_stream(self.STREAM_KEY)
        return {
            "length": info.get("length", 0),
            "first_entry": info.get("first-entry"),
            "last_entry": info.get("last-entry"),
            "groups": info.get("groups", 0),
        }
