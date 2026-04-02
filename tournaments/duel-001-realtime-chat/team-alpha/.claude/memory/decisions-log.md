# Architecture Decisions Log

## 2026-04-02: SQLite chosen over PostgreSQL
- Reason: Challenge allows SQLite, simpler deployment, aiosqlite provides async
- Trade-off: No real concurrent writes, but acceptable for chat demo

## 2026-04-02: In-memory presence over Redis
- Reason: Single-process app, no need for distributed state
- Trade-off: Presence lost on restart, acceptable for demo

## 2026-04-02: ConnectionManager singleton pattern
- Reason: Central registry for all WebSocket connections, easy room-based broadcast
- Trade-off: Not horizontally scalable, but matches single-process constraint

## 2026-04-02: JSON WebSocket protocol
- Reason: Human-readable, easy to debug, Pydantic can validate
- Format: {"type": "message|typing|join|leave|system", "data": {...}}
