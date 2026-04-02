"""Pydantic models and database schema."""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

# --- Request Models ---

class RoomCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)

# --- Response Models ---

class RoomResponse(BaseModel):
    id: int
    name: str
    created_at: str
    member_count: int = 0

class MessageResponse(BaseModel):
    id: int
    room_id: int
    username: str
    content: str
    created_at: str

class PresenceInfo(BaseModel):
    room_id: int
    room_name: str
    online_users: list[str]

class PaginatedMessages(BaseModel):
    messages: list[MessageResponse]
    total: int
    limit: int
    offset: int

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

CREATE INDEX IF NOT EXISTS idx_messages_room_id ON messages(room_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_room_members_room ON room_members(room_id);
"""
