"""WebSocket tests — Team Bravo."""
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


def test_ws_connect() -> None:
    """WebSocket connects with username."""
    c = TestClient(app)
    with c.websocket_connect("/ws?username=test") as ws:
        pass  # No exception = success


def test_ws_join_room_and_send() -> None:
    """Join room and send message via WebSocket."""
    c = TestClient(app)
    r = c.post("/rooms", json={"name": "ws-room"}).json()["id"]
    with c.websocket_connect("/ws?username=alice") as ws:
        ws.send_json({"type": "join_room", "room_id": r})
        sys_msg = ws.receive_json()
        assert sys_msg["type"] == "system"

        ws.send_json({"type": "send_message", "room_id": r, "content": "Hi!"})
        msg = ws.receive_json()
        assert msg["type"] == "message"
        assert msg["data"]["content"] == "Hi!"


def test_ws_room_isolation() -> None:
    """Messages don't leak between rooms."""
    c = TestClient(app)
    r1 = c.post("/rooms", json={"name": "iso-1"}).json()["id"]
    r2 = c.post("/rooms", json={"name": "iso-2"}).json()["id"]

    with c.websocket_connect("/ws?username=alice") as ws1:
        with c.websocket_connect("/ws?username=bob") as ws2:
            ws1.send_json({"type": "join_room", "room_id": r1})
            ws1.receive_json()
            ws2.send_json({"type": "join_room", "room_id": r2})
            ws2.receive_json()

            ws1.send_json({"type": "send_message", "room_id": r1, "content": "private"})
            m = ws1.receive_json()
            assert m["data"]["content"] == "private"

            ws2.send_json({"type": "send_message", "room_id": r2, "content": "other"})
            m2 = ws2.receive_json()
            assert m2["data"]["content"] == "other"


def test_ws_typing_broadcast() -> None:
    """Typing indicators reach other room members."""
    c = TestClient(app)
    r = c.post("/rooms", json={"name": "type-room"}).json()["id"]

    with c.websocket_connect("/ws?username=alice") as ws1:
        with c.websocket_connect("/ws?username=bob") as ws2:
            ws1.send_json({"type": "join_room", "room_id": r})
            ws1.receive_json()
            ws2.send_json({"type": "join_room", "room_id": r})
            ws2.receive_json()
            ws1.receive_json()  # bob join notification

            ws1.send_json({"type": "typing", "room_id": r, "is_typing": True})
            data = ws2.receive_json()
            assert data["type"] == "typing"
            assert data["data"]["username"] == "alice"


def test_ws_message_persisted() -> None:
    """Messages sent via WS are persisted and retrievable via REST."""
    c = TestClient(app)
    r = c.post("/rooms", json={"name": "persist-room"}).json()["id"]

    with c.websocket_connect("/ws?username=alice") as ws:
        ws.send_json({"type": "join_room", "room_id": r})
        ws.receive_json()
        ws.send_json({"type": "send_message", "room_id": r, "content": "Persisted!"})
        ws.receive_json()

    # Verify via REST
    resp = c.get(f"/rooms/{r}/messages")
    assert resp.status_code == 200
    msgs = resp.json()["messages"]
    assert len(msgs) == 1
    assert msgs[0]["content"] == "Persisted!"
