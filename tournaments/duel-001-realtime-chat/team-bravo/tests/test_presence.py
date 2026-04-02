"""Presence tests — Team Bravo."""
from __future__ import annotations

from src.presence import PresenceTracker


def test_join_shows_online() -> None:
    p = PresenceTracker()
    p.join(1, "alice")
    assert "alice" in p.get_online(1)


def test_leave_removes() -> None:
    p = PresenceTracker()
    p.join(1, "alice")
    p.leave(1, "alice")
    assert "alice" not in p.get_online(1)


def test_disconnect_clears_all() -> None:
    p = PresenceTracker()
    p.join(1, "alice")
    p.join(2, "alice")
    affected = p.disconnect("alice")
    assert set(affected) == {1, 2}
    assert p.get_online(1) == []


def test_multiple_users() -> None:
    p = PresenceTracker()
    p.join(1, "alice")
    p.join(1, "bob")
    assert p.get_online(1) == ["alice", "bob"]


def test_is_online() -> None:
    p = PresenceTracker()
    assert not p.is_online("x")
    p.join(1, "x")
    assert p.is_online("x")


def test_get_user_rooms() -> None:
    p = PresenceTracker()
    p.join(1, "alice")
    p.join(3, "alice")
    assert p.get_user_rooms("alice") == [1, 3]
