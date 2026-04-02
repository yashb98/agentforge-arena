# ADR-002: Singleton ConnectionManager

## Status: Accepted
## Context
Need to manage WebSocket connections organized by room.
## Decision
Singleton ConnectionManager class with dict-of-dicts: room_id → username → WebSocket.
## Consequences
- Pro: Simple, fast lookup, easy room-based broadcast
- Con: Single-process only, not horizontally scalable
