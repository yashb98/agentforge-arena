"""
AgentForge Arena — Tests for WebSocket Spectator Endpoint

Covers:
- Successful connection and confirmation message delivery
- Tournament-filtered event forwarding
- Events from other tournaments are NOT forwarded
- Non-JSON pubsub messages are silently skipped
- Clean disconnect and pubsub cleanup
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import orjson
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pubsub_message(data: dict) -> dict:
    """Build a fake Redis pubsub message dict containing orjson-encoded data."""
    return {"type": "message", "data": orjson.dumps(data)}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_pubsub() -> MagicMock:
    """Mock Redis pubsub object with async subscribe/get_message/unsubscribe/close."""
    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.close = AsyncMock()
    # Default: no messages — overridden per test.
    pubsub.get_message = AsyncMock(return_value=None)
    return pubsub


@pytest.fixture
def mock_redis(mock_pubsub: MagicMock) -> MagicMock:
    """Mock Redis client that returns mock_pubsub from .pubsub()."""
    redis = MagicMock()
    redis.pubsub = MagicMock(return_value=mock_pubsub)
    return redis


@pytest.fixture
def app(mock_redis: MagicMock) -> FastAPI:
    """Minimal FastAPI app with the spectator router and a mock redis on state."""
    from packages.api.src.ws.spectator import router

    application = FastAPI()
    application.include_router(router)
    application.state.redis = mock_redis
    return application


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_spectator_connects_and_receives_connected_message(
    app: FastAPI, mock_pubsub: MagicMock
) -> None:
    """Client receives {'type': 'connected', 'tournament_id': <id>} on connect.

    The pubsub loop is short-circuited by making get_message raise
    WebSocketDisconnect after the first (no-message) poll so the handler exits
    cleanly within the test.
    """
    tournament_id = "test-tournament-123"

    call_count = 0

    async def _get_message_then_disconnect(**_kwargs: object) -> None:  # type: ignore[return]
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect(code=1000)
        return None

    mock_pubsub.get_message = _get_message_then_disconnect

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/spectate/{tournament_id}") as ws:
            data = ws.receive_text()
            msg = json.loads(data)
            assert msg["type"] == "connected"
            assert msg["tournament_id"] == tournament_id


def test_spectator_subscribes_to_all_channels(
    app: FastAPI, mock_pubsub: MagicMock
) -> None:
    """pubsub.subscribe is called with all expected realtime channels."""
    from packages.api.src.ws.spectator import _CHANNELS

    tournament_id = "tourney-abc"

    async def _disconnect(**_kwargs: object) -> None:  # type: ignore[return]
        from fastapi import WebSocketDisconnect
        raise WebSocketDisconnect(code=1000)

    mock_pubsub.get_message = _disconnect

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/spectate/{tournament_id}") as ws:
            ws.receive_text()  # consume connected message

    mock_pubsub.subscribe.assert_awaited_once()
    # All configured channels must be present in the subscribe call.
    called_channels = mock_pubsub.subscribe.call_args[0]
    for channel in _CHANNELS:
        assert channel in called_channels


def test_spectator_forwards_matching_tournament_event(
    app: FastAPI, mock_pubsub: MagicMock
) -> None:
    """Events with a matching tournament_id are forwarded to the WebSocket client."""
    tournament_id = "tourney-xyz"
    event_payload = {
        "event_type": "tournament.phase.started",
        "tournament_id": tournament_id,
        "phase": "BUILD_SPRINT",
    }

    call_count = 0

    async def _get_message(**_kwargs: object) -> dict | None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_pubsub_message(event_payload)
        from fastapi import WebSocketDisconnect
        raise WebSocketDisconnect(code=1000)

    mock_pubsub.get_message = _get_message

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/spectate/{tournament_id}") as ws:
            _connected = ws.receive_text()  # consume connected message
            forwarded = ws.receive_text()
            msg = json.loads(forwarded)
            assert msg["tournament_id"] == tournament_id
            assert msg["event_type"] == "tournament.phase.started"
            assert msg["phase"] == "BUILD_SPRINT"


def test_spectator_drops_events_for_other_tournaments(
    app: FastAPI, mock_pubsub: MagicMock
) -> None:
    """Events whose tournament_id does not match are NOT forwarded."""
    tournament_id = "tourney-mine"
    other_event = {
        "event_type": "tournament.phase.started",
        "tournament_id": "tourney-other",
        "phase": "RESEARCH",
    }
    own_event = {
        "event_type": "tournament.completed",
        "tournament_id": tournament_id,
    }

    call_count = 0

    async def _get_message(**_kwargs: object) -> dict | None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_pubsub_message(other_event)  # should be dropped
        if call_count == 2:
            return _make_pubsub_message(own_event)  # should be forwarded
        from fastapi import WebSocketDisconnect
        raise WebSocketDisconnect(code=1000)

    mock_pubsub.get_message = _get_message

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/spectate/{tournament_id}") as ws:
            _connected = ws.receive_text()  # connected confirmation
            forwarded = ws.receive_text()
            msg = json.loads(forwarded)
            # Only the own event should arrive.
            assert msg["tournament_id"] == tournament_id
            assert msg["event_type"] == "tournament.completed"


def test_spectator_ignores_non_json_pubsub_messages(
    app: FastAPI, mock_pubsub: MagicMock
) -> None:
    """Non-JSON bytes in pubsub do not crash the handler."""
    tournament_id = "tourney-robust"

    call_count = 0

    async def _get_message(**_kwargs: object) -> dict | None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"type": "message", "data": b"not-valid-json{{{{"}
        from fastapi import WebSocketDisconnect
        raise WebSocketDisconnect(code=1000)

    mock_pubsub.get_message = _get_message

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/spectate/{tournament_id}") as ws:
            # Only the connected message should arrive; no error is raised.
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "connected"


def test_spectator_cleans_up_pubsub_on_disconnect(
    app: FastAPI, mock_pubsub: MagicMock
) -> None:
    """pubsub.unsubscribe and pubsub.close are called after disconnect."""

    async def _disconnect(**_kwargs: object) -> None:  # type: ignore[return]
        from fastapi import WebSocketDisconnect
        raise WebSocketDisconnect(code=1000)

    mock_pubsub.get_message = _disconnect

    with TestClient(app) as client:
        with client.websocket_connect("/ws/spectate/cleanup-test") as ws:
            ws.receive_text()  # connected message

    mock_pubsub.unsubscribe.assert_awaited_once()
    mock_pubsub.close.assert_awaited_once()
