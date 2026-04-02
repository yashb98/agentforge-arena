"""Message tests — Team Bravo."""
from __future__ import annotations

import pytest
from src import messages, rooms


async def test_save_message() -> None:
    """Save a message and verify fields."""
    room = await rooms.create_room("msg-room")
    msg = await messages.save_message(room.id, "alice", "Hi there")
    assert msg.content == "Hi there"
    assert msg.username == "alice"


async def test_get_messages_returns_recent_first() -> None:
    """Messages returned in descending ID order (most recent first)."""
    room = await rooms.create_room("order-room")
    m1 = await messages.save_message(room.id, "u", "first")
    m2 = await messages.save_message(room.id, "u", "second")
    result = await messages.get_messages(room.id)
    assert result.messages[0].id > result.messages[1].id


async def test_pagination_limit_offset() -> None:
    """Pagination respects limit and offset."""
    room = await rooms.create_room("page-room")
    for i in range(15):
        await messages.save_message(room.id, "u", f"m{i}")
    page1 = await messages.get_messages(room.id, limit=5, offset=0)
    page2 = await messages.get_messages(room.id, limit=5, offset=5)
    assert len(page1.messages) == 5
    assert len(page2.messages) == 5
    assert page1.total == 15
    # Pages should not overlap
    ids1 = {m.id for m in page1.messages}
    ids2 = {m.id for m in page2.messages}
    assert ids1.isdisjoint(ids2)


async def test_search_by_keyword() -> None:
    """Search finds matching messages."""
    room = await rooms.create_room("search-room")
    await messages.save_message(room.id, "a", "Python is great")
    await messages.save_message(room.id, "b", "I love JavaScript")
    await messages.save_message(room.id, "c", "Python rocks")
    results = await messages.search_messages(room.id, "Python")
    assert len(results) == 2


async def test_search_no_match() -> None:
    """Search with no match returns empty."""
    room = await rooms.create_room("nope-room")
    await messages.save_message(room.id, "a", "Hello")
    results = await messages.search_messages(room.id, "zzz")
    assert results == []


async def test_empty_room_messages() -> None:
    """Empty room has zero messages."""
    room = await rooms.create_room("ghost-room")
    result = await messages.get_messages(room.id)
    assert result.total == 0
    assert result.messages == []
