"""In-memory presence tracking — Team Bravo."""
from __future__ import annotations
from collections import defaultdict


class PresenceTracker:
    """Track online users per room with bidirectional lookup."""

    def __init__(self) -> None:
        self._rooms: dict[int, set[str]] = defaultdict(set)
        self._users: dict[str, set[int]] = defaultdict(set)

    def join(self, room_id: int, username: str) -> None:
        """Register user as present in a room."""
        self._rooms[room_id].add(username)
        self._users[username].add(room_id)

    def leave(self, room_id: int, username: str) -> None:
        """Remove user from a room."""
        self._rooms[room_id].discard(username)
        self._users[username].discard(room_id)
        if not self._rooms[room_id]:
            del self._rooms[room_id]

    def disconnect(self, username: str) -> list[int]:
        """Remove user from all rooms. Returns affected room IDs."""
        affected = list(self._users.get(username, []))
        for rid in affected:
            self._rooms[rid].discard(username)
            if not self._rooms[rid]:
                del self._rooms[rid]
        self._users.pop(username, None)
        return affected

    def get_online(self, room_id: int) -> list[str]:
        """Get sorted list of online users in a room."""
        return sorted(self._rooms.get(room_id, []))

    def get_user_rooms(self, username: str) -> list[int]:
        """Get rooms where user is present."""
        return sorted(self._users.get(username, []))

    def is_online(self, username: str) -> bool:
        """Check if user is in any room."""
        return bool(self._users.get(username))


presence = PresenceTracker()
