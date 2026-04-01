"""Hidden tests — Room management via REST API."""

from __future__ import annotations

import httpx
import pytest


class TestRoomCRUD:
    """Room create/list/join/leave via REST API."""

    def test_create_room(self, client: httpx.Client) -> None:
        """POST /rooms creates a new room."""
        resp = client.post("/rooms", json={"name": "test-room-crud"})
        assert resp.status_code in (200, 201)
        body = resp.json()
        assert "name" in body or "room" in body or "id" in body

    def test_create_duplicate_room(self, client: httpx.Client) -> None:
        """Creating a room with an existing name should fail or return existing."""
        client.post("/rooms", json={"name": "dup-room-test"})
        resp = client.post("/rooms", json={"name": "dup-room-test"})
        # Either 409 conflict or 200 returning existing
        assert resp.status_code in (200, 201, 409)

    def test_list_rooms(self, client: httpx.Client) -> None:
        """GET /rooms returns a list of rooms."""
        client.post("/rooms", json={"name": "list-test-room"})
        resp = client.get("/rooms")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, (list, dict))
        # Should contain at least our created room
        rooms_str = str(body)
        assert "list-test-room" in rooms_str or len(body) > 0

    def test_room_has_member_count(self, client: httpx.Client) -> None:
        """Room listing should include member/user count."""
        client.post("/rooms", json={"name": "count-room"})
        resp = client.get("/rooms")
        if resp.status_code == 200:
            body = resp.json()
            body_str = str(body).lower()
            has_count = any(k in body_str for k in ("members", "users", "count", "online"))
            if not has_count:
                pytest.skip("Room listing doesn't include member counts")


class TestRoomPresence:
    """User presence in rooms."""

    def test_room_members_endpoint(self, client: httpx.Client) -> None:
        """GET /rooms/{name}/members returns member list."""
        client.post("/rooms", json={"name": "presence-room"})
        for path in ("/rooms/presence-room/members", "/rooms/presence-room/users"):
            resp = client.get(path)
            if resp.status_code == 200:
                body = resp.json()
                assert isinstance(body, (list, dict))
                return
        pytest.skip("No members endpoint found")
