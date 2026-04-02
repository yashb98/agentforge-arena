# Architecture — Team Alpha Chat

## System Overview
```
┌──────────────────────────────────────────────┐
│                 FastAPI App                    │
├──────────────┬───────────────┬───────────────┤
│  REST Routes │  WS Endpoint  │   Lifespan    │
│  /rooms/*    │  /ws          │   DB init     │
│  /messages/* │               │   DB cleanup  │
│  /presence/* │               │               │
├──────────────┴───────┬───────┴───────────────┤
│  Business Logic      │  ConnectionManager     │
│  rooms.py            │  websocket_manager.py  │
│  messages.py         │  (singleton)           │
│  presence.py         │                        │
├──────────────────────┴───────────────────────┤
│              SQLite (aiosqlite)               │
│  rooms | room_members | messages              │
└──────────────────────────────────────────────┘
```

## Data Flow
1. **REST**: Client → FastAPI Route → Business Logic → SQLite → Response
2. **WebSocket**: Client → WS Endpoint → ConnectionManager → Broadcast to room
3. **Message persistence**: WS message → save to DB → broadcast to room

## Database Schema
- `rooms(id, name, created_at)` — Chat rooms
- `room_members(id, room_id, username, joined_at)` — Room membership
- `messages(id, room_id, username, content, created_at)` — Chat messages

## WebSocket Protocol
```json
// Client → Server
{"type": "join_room", "room_id": 1}
{"type": "send_message", "room_id": 1, "content": "Hello!"}
{"type": "typing", "room_id": 1, "is_typing": true}
{"type": "dm", "to_username": "bob", "content": "Hey"}
{"type": "leave_room", "room_id": 1}

// Server → Client
{"type": "system", "data": {"message": "alice joined the room"}}
{"type": "message", "data": {"id": 1, "username": "alice", "content": "Hello!"}}
{"type": "typing", "data": {"username": "alice", "is_typing": true}}
{"type": "dm", "data": {"from": "alice", "content": "Hey"}}
```

## Key Decisions
- **Singleton ConnectionManager** — simple, no distributed state needed
- **In-memory presence** — ephemeral by nature, no need to persist
- **SQLite with WAL** — good enough for demo, async via aiosqlite
- **Repository pattern** — DB access isolated in rooms.py, messages.py
