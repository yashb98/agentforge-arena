"""Message tests — Team Alpha."""
from __future__ import annotations

import pytest
from src import messages, rooms


async def test_save_and_retrieve_message() -> None:
    """Save a message and retrieve it."""
    room = await rooms.create_room("msg-test")
    msg = await messages.save_message(room.id, "alice", "Hello!")
    assert msg.content == "Hello!"
    assert msg.username == "alice"
    assert msg.room_id == room.id


async def test_get_messages_pagination() -> None:
    """Messages are paginated correctly."""
    room = await rooms.create_room("page-test")
    for i in range(10):
        await messages.save_message(room.id, "user", f"msg-{i}")
    result = await messages.get_messages(room.id, limit=3, offset=0)
    assert len(result.messages) == 3
    assert result.total == 10
    assert result.limit == 3


async def test_get_messages_empty_room() -> None:
    """Empty room returns no messages."""
    room = await rooms.create_room("empty-test")
    result = await messages.get_messages(room.id)
    assert len(result.messages) == 0
    assert result.total == 0


async def test_search_messages() -> None:
    """Search finds messages containing keyword."""
    room = await rooms.create_room("search-test")
    await messages.save_message(room.id, "alice", "Hello world")
    await messages.save_message(room.id, "bob", "Goodbye world")
    await messages.save_message(room.id, "carol", "Hi there")
    results = await messages.search_messages(room.id, "world")
    assert len(results) == 2


async def test_search_no_results() -> None:
    """Search with no matches returns empty list."""
    room = await rooms.create_room("nosearch-test")
    await messages.save_message(room.id, "alice", "Hello")
    results = await messages.search_messages(room.id, "xyz123")
    assert len(results) == 0
