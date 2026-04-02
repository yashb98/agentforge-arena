# ADR-001: SQLite for Chat Storage

## Status: Accepted
## Context
Need a database for rooms and message persistence. Options: PostgreSQL, SQLite, Redis.
## Decision
SQLite via aiosqlite. Single-file, zero-config, async support, sufficient for demo scale.
## Consequences
- Pro: No external dependencies, easy testing with :memory:
- Con: Not suitable for horizontal scaling or high write throughput
