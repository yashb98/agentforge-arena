"""Presence tracking tests — Team Alpha."""
from __future__ import annotations

from src.presence import PresenceTracker


def test_user_join_and_presence() -> None:
    """User appears in room after joining."""
    p = PresenceTracker()
    p.user_joined(1, "alice")
    assert "alice" in p.get_room_users(1)


def test_user_leave_removes_presence() -> None:
    """User disappears from room after leaving."""
    p = PresenceTracker()
    p.user_joined(1, "alice")
    p.user_left(1, "alice")
    assert "alice" not in p.get_room_users(1)


def test_user_disconnect_clears_all_rooms() -> None:
    """Disconnect removes user from all rooms."""
    p = PresenceTracker()
    p.user_joined(1, "alice")
    p.user_joined(2, "alice")
    rooms = p.user_disconnected("alice")
    assert set(rooms) == {1, 2}
    assert p.get_room_users(1) == []
    assert p.get_room_users(2) == []


def test_multiple_users_in_room() -> None:
    """Multiple users tracked correctly."""
    p = PresenceTracker()
    p.user_joined(1, "alice")
    p.user_joined(1, "bob")
    users = p.get_room_users(1)
    assert users == ["alice", "bob"]


def test_is_online() -> None:
    """is_online reflects current state."""
    p = PresenceTracker()
    assert not p.is_online("alice")
    p.user_joined(1, "alice")
    assert p.is_online("alice")
    p.user_disconnected("alice")
    assert not p.is_online("alice")


def test_get_all_online() -> None:
    """get_all_online returns full presence map."""
    p = PresenceTracker()
    p.user_joined(1, "alice")
    p.user_joined(2, "bob")
    online = p.get_all_online()
    assert 1 in online
    assert 2 in online
