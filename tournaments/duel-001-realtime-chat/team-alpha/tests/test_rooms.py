"""Room CRUD tests — Team Alpha."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


async def test_create_room(client: AsyncClient) -> None:
    """Creating a room returns 201 with room data."""
    resp = await client.post("/rooms", json={"name": "general"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "general"
    assert data["id"] >= 1


async def test_create_duplicate_room(client: AsyncClient) -> None:
    """Creating a duplicate room returns 409."""
    await client.post("/rooms", json={"name": "dup"})
    resp = await client.post("/rooms", json={"name": "dup"})
    assert resp.status_code == 409


async def test_list_rooms(client: AsyncClient) -> None:
    """Listing rooms returns all created rooms."""
    await client.post("/rooms", json={"name": "room-a"})
    await client.post("/rooms", json={"name": "room-b"})
    resp = await client.get("/rooms")
    assert resp.status_code == 200
    rooms = resp.json()
    assert len(rooms) == 2


async def test_get_room(client: AsyncClient) -> None:
    """Getting a specific room by ID."""
    create_resp = await client.post("/rooms", json={"name": "test-room"})
    room_id = create_resp.json()["id"]
    resp = await client.get(f"/rooms/{room_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "test-room"


async def test_get_nonexistent_room(client: AsyncClient) -> None:
    """Getting a non-existent room returns 404."""
    resp = await client.get("/rooms/9999")
    assert resp.status_code == 404


async def test_join_room(client: AsyncClient) -> None:
    """Joining a room succeeds."""
    create_resp = await client.post("/rooms", json={"name": "join-test"})
    room_id = create_resp.json()["id"]
    resp = await client.post(f"/rooms/{room_id}/join?username=alice")
    assert resp.status_code == 200
    assert resp.json()["joined"] is True


async def test_leave_room(client: AsyncClient) -> None:
    """Leaving a room after joining."""
    create_resp = await client.post("/rooms", json={"name": "leave-test"})
    room_id = create_resp.json()["id"]
    await client.post(f"/rooms/{room_id}/join?username=bob")
    resp = await client.post(f"/rooms/{room_id}/leave?username=bob")
    assert resp.status_code == 200
    assert resp.json()["left"] is True
