# Architecture Rules
- WebSocket messages are JSON: {"type": str, "data": dict}
- Rooms are the primary isolation boundary
- Presence is ephemeral (in-memory), messages are persistent (SQLite)
- All DB operations go through repository functions, not raw SQL in routes
- REST for CRUD, WebSocket for real-time only
