"""Pydantic models and database schema — Team Bravo."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# --- WebSocket Message Protocol (typed events) ---


class WSJoinRoom(BaseModel):
    """WebSocket event: join a room."""

    type: Literal["join_room"] = "join_room"
    room_id: int


class WSLeaveRoom(BaseModel):
    """WebSocket event: leave a room."""

    type: Literal["leave_room"] = "leave_room"
    room_id: int


class WSSendMessage(BaseModel):
    """WebSocket event: send a message."""

    type: Literal["send_message"] = "send_message"
    room_id: int
    content: str = Field(..., min_length=1, max_length=5000)


class WSTyping(BaseModel):
    """WebSocket event: typing indicator."""

    type: Literal["typing"] = "typing"
    room_id: int
    is_typing: bool = True


class WSDirectMessage(BaseModel):
    """WebSocket event: direct message."""

    type: Literal["dm"] = "dm"
    to_username: str
    content: str = Field(..., min_length=1, max_length=5000)


# --- REST Models ---


class RoomCreate(BaseModel):
    """Request body for creating a room."""

    name: str = Field(..., min_length=1, max_length=100, description="Unique room name")


class RoomResponse(BaseModel):
    """Response body for a room."""

    id: int = Field(..., description="Room ID")
    name: str = Field(..., description="Room name")
    created_at: str = Field(..., description="Timestamp of creation")
    member_count: int = Field(default=0, description="Number of members")


class MessageCreate(BaseModel):
    """Request body for sending a message via REST."""

    room_id: int = Field(..., description="Target room ID")
    username: str = Field(..., min_length=1, description="Sender username")
    content: str = Field(..., min_length=1, max_length=5000, description="Message content")


class MessageResponse(BaseModel):
    """Response body for a persisted message."""

    id: int = Field(..., description="Message ID")
    room_id: int = Field(..., description="Room ID")
    username: str = Field(..., description="Author username")
    content: str = Field(..., description="Message text")
    created_at: str = Field(..., description="Timestamp")


class PaginatedMessages(BaseModel):
    """Paginated list of messages."""

    messages: list[MessageResponse] = Field(default_factory=list)
    total: int = Field(..., description="Total number of messages")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Page offset")


class PresenceResponse(BaseModel):
    """Online users for a room."""

    room_id: int = Field(..., description="Room ID")
    online_users: list[str] = Field(default_factory=list, description="Online usernames")


# --- Database DDL ---

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS room_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    username TEXT NOT NULL,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(room_id, username)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    username TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_id);
CREATE INDEX IF NOT EXISTS idx_messages_content ON messages(content);
"""
