"""
AgentForge Arena — WebSocket Spectator Endpoint

Streams real-time tournament events to connected spectator clients.

Clients connect to /ws/spectate/{tournament_id} and receive a stream of
JSON-encoded events filtered to the requested tournament. Events are sourced
from Redis Pub/Sub channels published by the platform's event bus.
"""

from __future__ import annotations

import asyncio
import logging

import orjson
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# Redis Pub/Sub channels to subscribe to for tournament events.
_CHANNELS: list[str] = [
    "arena:realtime:tournament.phase.*",
    "arena:realtime:tournament.team.*",
    "arena:realtime:agent.tool.*",
    "arena:realtime:tournament.budget.*",
    "arena:realtime:tournament.completed",
]

# Polling interval (seconds) between pubsub get_message calls.
_POLL_INTERVAL: float = 1.0


@router.websocket("/ws/spectate/{tournament_id}")
async def spectate_tournament(websocket: WebSocket, tournament_id: str) -> None:
    """Stream real-time events for *tournament_id* to a WebSocket client.

    Protocol:
    1. Accept the connection.
    2. Send a ``{"type": "connected", "tournament_id": "<id>"}`` confirmation.
    3. Subscribe to all arena realtime Redis Pub/Sub channels.
    4. Forward events that match *tournament_id* as JSON text frames.
    5. On disconnect, unsubscribe and clean up resources.
    """
    await websocket.accept()
    logger.info("Spectator connected for tournament %s", tournament_id)

    # Confirm connection to the client.
    await websocket.send_text(
        orjson.dumps({"type": "connected", "tournament_id": tournament_id}).decode()
    )

    redis = websocket.app.state.redis
    pubsub = redis.pubsub()

    try:
        # Subscribe to all realtime channels.
        await pubsub.subscribe(*_CHANNELS)
        logger.debug(
            "Subscribed to %d channels for tournament %s", len(_CHANNELS), tournament_id
        )

        # Event forwarding loop — exits on WebSocketDisconnect.
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True)

            if message is not None:
                raw = message.get("data")
                if isinstance(raw, (bytes, bytearray)):
                    try:
                        event: dict = orjson.loads(raw)
                    except orjson.JSONDecodeError:
                        logger.warning(
                            "Received non-JSON message on pubsub for tournament %s",
                            tournament_id,
                        )
                        continue

                    # Forward only events belonging to this tournament.
                    if event.get("tournament_id") == tournament_id:
                        await websocket.send_text(
                            orjson.dumps(event).decode()
                        )

            await asyncio.sleep(_POLL_INTERVAL)

    except WebSocketDisconnect:
        logger.info("Spectator disconnected from tournament %s", tournament_id)
    finally:
        await pubsub.unsubscribe(*_CHANNELS)
        await pubsub.close()
        logger.debug("Pub/Sub cleaned up for tournament %s", tournament_id)
