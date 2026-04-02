# Architecture — Team Bravo Chat (Event-Driven)

## System Overview
```
┌──────────────────────────────────────────────┐
│              FastAPI App                       │
├──────────────┬───────────────┬───────────────┤
│  REST API    │  WS Gateway   │   Lifespan    │
│  Rooms CRUD  │  Event Router │   DB Init     │
│  Messages    │  ┌──────────┐ │               │
│  Presence    │  │ Handlers │ │               │
│              │  │ join     │ │               │
│              │  │ message  │ │               │
│              │  │ typing   │ │               │
│              │  │ dm       │ │               │
│              │  └──────────┘ │               │
├──────────────┴───────┬───────┴───────────────┤
│  Service Layer       │  ConnectionManager     │
│  rooms.py            │  (event emitter)       │
│  messages.py         │                        │
│  presence.py         │                        │
├──────────────────────┴───────────────────────┤
│           SQLite (WAL mode, aiosqlite)        │
│  rooms | room_members | messages              │
└──────────────────────────────────────────────┘
```

## Key Differentiator: Event-Driven Dispatch
Instead of a monolithic if/elif chain, WebSocket messages are routed through a handler registry:
```python
_HANDLERS = {
    "join_room": _handle_join,
    "send_message": _handle_message,
    "typing": _handle_typing,
    "dm": _handle_dm,
}
```
Each handler is an independent async function — easy to test, extend, and debug.

## Database Schema
Same as standard: rooms, room_members, messages tables with proper indexes.

## WebSocket Protocol
Type-discriminated JSON events. Each has a dedicated Pydantic model for validation.

## Testing Strategy (TDD)
1. Tests written BEFORE implementation
2. Each module has matching test file
3. In-memory SQLite for isolation
4. Starlette TestClient for WebSocket tests
