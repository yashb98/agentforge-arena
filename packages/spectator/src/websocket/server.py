"""
AgentForge Arena — Spectator WebSocket Server

Real-time streaming of tournament events to spectator clients.
Uses Socket.IO for WebSocket communication with automatic reconnection.

Architecture:
  Redis Pub/Sub → SpectatorServer → Socket.IO → Browser Clients
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import orjson
import redis.asyncio as aioredis
import socketio

from packages.shared.src.types.models import ArenaEvent

logger = logging.getLogger(__name__)


class SpectatorServer:
    """Socket.IO server for real-time spectator streaming."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._sio = socketio.AsyncServer(
            async_mode="asgi",
            cors_allowed_origins="*",
            logger=False,
            engineio_logger=False,
        )
        self._app = socketio.ASGIApp(self._sio)
        self._active_subscriptions: dict[str, asyncio.Task] = {}

        # Register event handlers
        self._sio.on("connect", self._on_connect)
        self._sio.on("disconnect", self._on_disconnect)
        self._sio.on("join_tournament", self._on_join_tournament)
        self._sio.on("leave_tournament", self._on_leave_tournament)

    @property
    def asgi_app(self) -> socketio.ASGIApp:
        """Get the ASGI app for mounting in FastAPI."""
        return self._app

    # ========================================================
    # Socket.IO Event Handlers
    # ========================================================

    async def _on_connect(self, sid: str, environ: dict) -> None:
        """Handle new spectator connection."""
        logger.info("Spectator connected: %s", sid)
        await self._sio.emit("welcome", {"message": "Connected to AgentForge Arena"}, to=sid)

    async def _on_disconnect(self, sid: str) -> None:
        """Handle spectator disconnection."""
        logger.info("Spectator disconnected: %s", sid)

    async def _on_join_tournament(self, sid: str, data: dict) -> None:
        """Spectator joins a tournament room for live updates."""
        tournament_id = data.get("tournament_id", "")
        if not tournament_id:
            await self._sio.emit("error", {"message": "tournament_id required"}, to=sid)
            return

        room = f"tournament:{tournament_id}"
        self._sio.enter_room(sid, room)
        logger.info("Spectator %s joined room %s", sid, room)

        # Start Redis subscription for this tournament if not already running
        if room not in self._active_subscriptions:
            task = asyncio.create_task(self._subscribe_tournament(tournament_id))
            self._active_subscriptions[room] = task

        await self._sio.emit(
            "joined",
            {"tournament_id": tournament_id, "message": "Streaming live events"},
            to=sid,
        )

    async def _on_leave_tournament(self, sid: str, data: dict) -> None:
        """Spectator leaves a tournament room."""
        tournament_id = data.get("tournament_id", "")
        room = f"tournament:{tournament_id}"
        self._sio.leave_room(sid, room)
        logger.info("Spectator %s left room %s", sid, room)

    # ========================================================
    # Redis → Socket.IO Bridge
    # ========================================================

    async def _subscribe_tournament(self, tournament_id: str) -> None:
        """Subscribe to Redis Pub/Sub for a tournament and forward to Socket.IO."""
        room = f"tournament:{tournament_id}"
        pubsub = self._redis.pubsub()

        # Subscribe to tournament-specific events
        channel = f"tournament:{tournament_id}:events"
        await pubsub.subscribe(channel)

        logger.info("Subscribed to Redis channel: %s", channel)

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    event_data = orjson.loads(message["data"])
                    event_type = event_data.get("type", "unknown")

                    # Forward to all spectators in the room
                    await self._sio.emit(
                        event_type,
                        event_data,
                        room=room,
                    )
                except (orjson.JSONDecodeError, KeyError) as e:
                    logger.warning("Failed to parse event: %s", e)

        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            if room in self._active_subscriptions:
                del self._active_subscriptions[room]

    # ========================================================
    # Direct Event Broadcasting
    # ========================================================

    async def broadcast_event(self, tournament_id: str, event: ArenaEvent) -> None:
        """Directly broadcast an event to spectators (used by internal services)."""
        room = f"tournament:{tournament_id}"
        await self._sio.emit(
            event.event_type,
            event.model_dump(mode="json"),
            room=room,
        )

    async def broadcast_commentary(
        self, tournament_id: str, commentary: str, category: str = "insight"
    ) -> None:
        """Broadcast tutor commentary to spectators."""
        room = f"tournament:{tournament_id}"
        await self._sio.emit(
            "tutor.commentary",
            {"commentary": commentary, "category": category},
            room=room,
        )

    async def broadcast_agent_status(
        self,
        tournament_id: str,
        team_id: str,
        agent_role: str,
        status: str,
        detail: str = "",
    ) -> None:
        """Broadcast agent status update to spectators."""
        room = f"tournament:{tournament_id}"
        await self._sio.emit(
            "agent.status",
            {
                "team_id": team_id,
                "agent_role": agent_role,
                "status": status,
                "detail": detail,
            },
            room=room,
        )

    # ========================================================
    # Lifecycle
    # ========================================================

    async def shutdown(self) -> None:
        """Clean up all subscriptions."""
        for task in self._active_subscriptions.values():
            task.cancel()
        await asyncio.gather(*self._active_subscriptions.values(), return_exceptions=True)
        self._active_subscriptions.clear()
