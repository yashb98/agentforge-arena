"""Shared fixtures for Real-Time Chat hidden test suite."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import httpx
import pytest
import websockets

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"


@pytest.fixture()
def client() -> httpx.Client:
    """Synchronous HTTP client."""
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


@pytest.fixture()
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as c:
        yield c


async def connect_ws(username: str, room: str | None = None) -> websockets.WebSocketClientProtocol:
    """Connect a WebSocket client with optional room."""
    url = f"{WS_URL}?username={username}"
    if room:
        url += f"&room={room}"
    ws = await websockets.connect(url, close_timeout=5)
    return ws


@pytest.fixture()
def unique_room() -> str:
    """Generate a unique room name for test isolation."""
    import uuid
    return f"test-room-{uuid.uuid4().hex[:8]}"
