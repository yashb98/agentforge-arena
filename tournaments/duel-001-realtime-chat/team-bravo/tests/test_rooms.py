"""Room tests — Team Bravo (TDD-driven)."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


async def test_create_room_returns_201(client: AsyncClient) -> None:
    """POST /rooms creates room and returns 201."""
    resp = await client.post("/rooms", json={"name": "lobby"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "lobby"
    assert "id" in resp.json()


async def test_create_room_duplicate_returns_409(client: AsyncClient) -> None:
    """Duplicate room name returns 409."""
    await client.post("/rooms", json={"name": "unique"})
    resp = await client.post("/rooms", json={"name": "unique"})
    assert resp.status_code == 409


async def test_list_rooms_empty(client: AsyncClient) -> None:
    """No rooms returns empty list."""
    resp = await client.get("/rooms")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_rooms_multiple(client: AsyncClient) -> None:
    """Multiple rooms returned in list."""
    await client.post("/rooms", json={"name": "alpha"})
    await client.post("/rooms", json={"name": "beta"})
    resp = await client.get("/rooms")
    assert len(resp.json()) == 2


async def test_get_room_by_id(client: AsyncClient) -> None:
    """GET /rooms/:id returns room details."""
    create = await client.post("/rooms", json={"name": "detail"})
    rid = create.json()["id"]
    resp = await client.get(f"/rooms/{rid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "detail"


async def test_get_room_not_found(client: AsyncClient) -> None:
    """Non-existent room returns 404."""
    resp = await client.get("/rooms/9999")
    assert resp.status_code == 404


async def test_join_room(client: AsyncClient) -> None:
    """Join room succeeds."""
    r = await client.post("/rooms", json={"name": "joinable"})
    rid = r.json()["id"]
    resp = await client.post(f"/rooms/{rid}/join?username=tester")
    assert resp.json()["joined"] is True


async def test_leave_room_after_join(client: AsyncClient) -> None:
    """Leave room after joining."""
    r = await client.post("/rooms", json={"name": "leaveable"})
    rid = r.json()["id"]
    await client.post(f"/rooms/{rid}/join?username=user1")
    resp = await client.post(f"/rooms/{rid}/leave?username=user1")
    assert resp.json()["left"] is True


async def test_join_nonexistent_room(client: AsyncClient) -> None:
    """Joining non-existent room returns 404."""
    resp = await client.post("/rooms/9999/join?username=ghost")
    assert resp.status_code == 404
