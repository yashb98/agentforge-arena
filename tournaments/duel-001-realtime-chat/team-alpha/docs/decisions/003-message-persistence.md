# ADR-003: Persist All Messages to SQLite

## Status: Accepted
## Context
Messages need to survive reconnection. Options: in-memory buffer, Redis, SQLite.
## Decision
All messages saved to SQLite immediately on send. Retrieved via paginated REST API.
## Consequences
- Pro: Full history, survives restart, searchable
- Con: Write latency per message (mitigated by WAL mode)
