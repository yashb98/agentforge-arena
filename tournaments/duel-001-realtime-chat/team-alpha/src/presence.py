"""In-memory user presence tracking."""
from __future__ import annotations
from collections import defaultdict


class PresenceTracker:
    """Track which users are online in which rooms."""

    def __init__(self) -> None:
        self._room_users: dict[int, set[str]] = defaultdict(set)
        self._user_rooms: dict[str, set[int]] = defaultdict(set)

    def user_joined(self, room_id: int, username: str) -> None:
        """Mark user as present in a room."""
        self._room_users[room_id].add(username)
        self._user_rooms[username].add(room_id)

    def user_left(self, room_id: int, username: str) -> None:
        """Mark user as absent from a room."""
        self._room_users[room_id].discard(username)
        self._user_rooms[username].discard(room_id)
        if not self._room_users[room_id]:
            del self._room_users[room_id]

    def user_disconnected(self, username: str) -> list[int]:
        """Remove user from all rooms. Returns list of room IDs they left."""
        rooms = list(self._user_rooms.get(username, set()))
        for room_id in rooms:
            self._room_users[room_id].discard(username)
            if not self._room_users[room_id]:
                del self._room_users[room_id]
        self._user_rooms.pop(username, None)
        return rooms

    def get_room_users(self, room_id: int) -> list[str]:
        """Get list of online users in a room."""
        return sorted(self._room_users.get(room_id, set()))

    def get_all_online(self) -> dict[int, list[str]]:
        """Get all online users grouped by room."""
        return {rid: sorted(users) for rid, users in self._room_users.items()}

    def is_online(self, username: str) -> bool:
        """Check if a user is online in any room."""
        return username in self._user_rooms and len(self._user_rooms[username]) > 0


presence = PresenceTracker()
