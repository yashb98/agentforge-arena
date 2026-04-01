"""Hidden tests — WebSocket connection and messaging."""

from __future__ import annotations

import asyncio
import json

import pytest
import websockets

from conftest import WS_URL, connect_ws


class TestWebSocketConnection:
    """WebSocket connection lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_succeeds(self) -> None:
        """Client can connect via WebSocket."""
        ws = await connect_ws("test_user_1")
        assert ws.open
        await ws.close()

    @pytest.mark.asyncio
    async def test_multiple_clients_connect(self) -> None:
        """Multiple clients can connect simultaneously."""
        clients = []
        for i in range(5):
            ws = await connect_ws(f"multi_user_{i}")
            clients.append(ws)
            assert ws.open
        for ws in clients:
            await ws.close()

    @pytest.mark.asyncio
    async def test_send_message_to_room(self, unique_room: str) -> None:
        """Message sent to a room is received by other members."""
        ws1 = await connect_ws("sender", unique_room)
        ws2 = await connect_ws("receiver", unique_room)

        # Give time for both to join
        await asyncio.sleep(0.5)

        # Send message
        msg = json.dumps({"type": "message", "room": unique_room, "content": "Hello!"})
        await ws1.send(msg)

        # Receiver should get the message
        try:
            raw = await asyncio.wait_for(ws2.recv(), timeout=5.0)
            data = json.loads(raw)
            assert "Hello!" in str(data)
        except asyncio.TimeoutError:
            pytest.fail("Receiver did not get message within 5 seconds")
        finally:
            await ws1.close()
            await ws2.close()

    @pytest.mark.asyncio
    async def test_room_isolation(self, unique_room: str) -> None:
        """Messages in one room don't leak to another."""
        room_a = f"{unique_room}_a"
        room_b = f"{unique_room}_b"

        ws_a = await connect_ws("user_a", room_a)
        ws_b = await connect_ws("user_b", room_b)

        await asyncio.sleep(0.5)

        # Send message to room_a
        await ws_a.send(json.dumps({"type": "message", "room": room_a, "content": "secret"}))

        # room_b user should NOT receive it
        try:
            raw = await asyncio.wait_for(ws_b.recv(), timeout=2.0)
            data = json.loads(raw)
            # If we get a message, it should NOT contain our secret
            assert "secret" not in str(data), "Message leaked between rooms"
        except asyncio.TimeoutError:
            pass  # Good — no message received
        finally:
            await ws_a.close()
            await ws_b.close()


class TestTypingIndicators:
    """Typing indicator tests."""

    @pytest.mark.asyncio
    async def test_typing_broadcast(self, unique_room: str) -> None:
        """Typing indicator is broadcast to other room members."""
        ws1 = await connect_ws("typer", unique_room)
        ws2 = await connect_ws("watcher", unique_room)

        await asyncio.sleep(0.5)

        await ws1.send(json.dumps({"type": "typing", "room": unique_room, "is_typing": True}))

        try:
            raw = await asyncio.wait_for(ws2.recv(), timeout=3.0)
            data = json.loads(raw)
            assert "typing" in str(data).lower() or "typer" in str(data)
        except asyncio.TimeoutError:
            pytest.skip("Typing indicators not implemented")
        finally:
            await ws1.close()
            await ws2.close()
