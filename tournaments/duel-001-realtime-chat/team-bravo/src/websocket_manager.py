"""Event-driven WebSocket connection manager — Team Bravo."""
from __future__ import annotations

import logging
from collections import defaultdict
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections with event-driven dispatch."""

    def __init__(self) -> None:
        self._rooms: dict[int, dict[str, WebSocket]] = defaultdict(dict)
        self._user_connections: dict[str, WebSocket] = {}

    async def connect(self, ws: WebSocket, username: str) -> None:
        """Accept and register a WebSocket connection."""
        await ws.accept()
        self._user_connections[username] = ws

    def disconnect(self, username: str) -> list[int]:
        """Unregister user from all rooms. Returns affected room IDs."""
        affected = []
        for room_id, members in list(self._rooms.items()):
            if username in members:
                del members[username]
                affected.append(room_id)
                if not members:
                    del self._rooms[room_id]
        self._user_connections.pop(username, None)
        return affected

    def add_to_room(self, room_id: int, username: str) -> None:
        """Register user's WebSocket in a room."""
        ws = self._user_connections.get(username)
        if ws:
            self._rooms[room_id][username] = ws

    def remove_from_room(self, room_id: int, username: str) -> None:
        """Remove user from a room."""
        if room_id in self._rooms:
            self._rooms[room_id].pop(username, None)
            if not self._rooms[room_id]:
                del self._rooms[room_id]

    async def emit(self, room_id: int, event: dict, skip: str | None = None) -> None:
        """Emit an event to all members of a room."""
        members = self._rooms.get(room_id, {})
        for uname, ws in list(members.items()):
            if uname == skip:
                continue
            try:
                await ws.send_json(event)
            except Exception:
                logger.warning("Send failed for %s, cleaning up", uname)
                members.pop(uname, None)

    async def send_dm(self, to_user: str, event: dict) -> bool:
        """Send a direct message to a user."""
        ws = self._user_connections.get(to_user)
        if not ws:
            return False
        try:
            await ws.send_json(event)
            return True
        except Exception:
            return False

    def room_members(self, room_id: int) -> list[str]:
        """Get connected usernames in a room."""
        return list(self._rooms.get(room_id, {}).keys())


manager = ConnectionManager()
