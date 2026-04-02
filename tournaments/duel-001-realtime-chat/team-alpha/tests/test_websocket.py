"""WebSocket integration tests — Team Alpha."""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient
from src.main import app
from src import database


@pytest.fixture(autouse=True)
async def setup():
    await database.init_db(":memory:")
    yield
    await database.close_db()


def test_websocket_connect() -> None:
    """WebSocket connects successfully."""
    client = TestClient(app)
    with client.websocket_connect("/ws?username=alice") as ws:
        # Connection succeeded if no exception
        pass


def test_websocket_join_and_message() -> None:
    """User can join room and send messages."""
    client = TestClient(app)
    # Create a room first
    resp = client.post("/rooms", json={"name": "ws-test"})
    room_id = resp.json()["id"]

    with client.websocket_connect("/ws?username=alice") as ws:
        ws.send_json({"type": "join_room", "room_id": room_id})
        # Receive system join message
        data = ws.receive_json()
        assert data["type"] == "system"
        assert "joined" in data["data"]["message"]

        # Send a chat message
        ws.send_json({"type": "send_message", "room_id": room_id, "content": "Hello!"})
        data = ws.receive_json()
        assert data["type"] == "message"
        assert data["data"]["content"] == "Hello!"


def test_websocket_room_isolation() -> None:
    """Messages in one room don't leak to another."""
    client = TestClient(app)
    r1 = client.post("/rooms", json={"name": "room-1"}).json()["id"]
    r2 = client.post("/rooms", json={"name": "room-2"}).json()["id"]

    with client.websocket_connect("/ws?username=alice") as ws1:
        with client.websocket_connect("/ws?username=bob") as ws2:
            ws1.send_json({"type": "join_room", "room_id": r1})
            ws1.receive_json()  # system message

            ws2.send_json({"type": "join_room", "room_id": r2})
            ws2.receive_json()  # system message

            # Alice sends to room 1
            ws1.send_json({"type": "send_message", "room_id": r1, "content": "secret"})
            msg = ws1.receive_json()
            assert msg["data"]["content"] == "secret"

            # Bob in room 2 should NOT receive it — no data pending
            # (If we try receive_json here it would block, so we verify
            # by checking Bob can still send/receive in room 2)
            ws2.send_json({"type": "send_message", "room_id": r2, "content": "other"})
            msg2 = ws2.receive_json()
            assert msg2["data"]["content"] == "other"


def test_websocket_typing_indicator() -> None:
    """Typing indicators broadcast to room members."""
    client = TestClient(app)
    r = client.post("/rooms", json={"name": "typing-test"}).json()["id"]

    with client.websocket_connect("/ws?username=alice") as ws1:
        with client.websocket_connect("/ws?username=bob") as ws2:
            ws1.send_json({"type": "join_room", "room_id": r})
            ws1.receive_json()  # alice join system msg

            ws2.send_json({"type": "join_room", "room_id": r})
            ws2.receive_json()  # bob join (to bob)
            ws1.receive_json()  # bob join (to alice)

            # Alice starts typing
            ws1.send_json({"type": "typing", "room_id": r, "is_typing": True})
            data = ws2.receive_json()
            assert data["type"] == "typing"
            assert data["data"]["username"] == "alice"
            assert data["data"]["is_typing"] is True
