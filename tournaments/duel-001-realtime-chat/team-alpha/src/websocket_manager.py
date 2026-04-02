"""WebSocket connection manager — singleton pattern."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections organized by room."""

    def __init__(self) -> None:
        self._connections: dict[int, dict[str, WebSocket]] = defaultdict(dict)
        self._user_ws: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, username: str) -> None:
        """Accept a WebSocket connection."""
        await websocket.accept()
        self._user_ws[username] = websocket

    def disconnect(self, username: str) -> list[int]:
        """Remove user from all rooms. Returns room IDs they were in."""
        rooms_left = []
        for room_id, users in list(self._connections.items()):
            if username in users:
                del users[username]
                rooms_left.append(room_id)
                if not users:
                    del self._connections[room_id]
        self._user_ws.pop(username, None)
        return rooms_left

    def join_room(self, room_id: int, username: str) -> None:
        """Add user's WebSocket to a room."""
        ws = self._user_ws.get(username)
        if ws:
            self._connections[room_id][username] = ws

    def leave_room(self, room_id: int, username: str) -> None:
        """Remove user from a room's connections."""
        if room_id in self._connections:
            self._connections[room_id].pop(username, None)
            if not self._connections[room_id]:
                del self._connections[room_id]

    async def broadcast_to_room(self, room_id: int, message: dict, exclude: str | None = None) -> None:
        """Send a message to all users in a room."""
        users = self._connections.get(room_id, {})
        for username, ws in list(users.items()):
            if username == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                logger.debug("Failed to send to %s, removing", username)
                users.pop(username, None)

    async def send_to_user(self, username: str, message: dict) -> bool:
        """Send a direct message to a specific user."""
        ws = self._user_ws.get(username)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            return False

    def get_room_connections(self, room_id: int) -> list[str]:
        """Get list of connected usernames in a room."""
        return list(self._connections.get(room_id, {}).keys())


manager = ConnectionManager()
