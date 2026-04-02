# ADR-001: SQLite with WAL Mode

## Status: Accepted
## Context
Need persistent storage for rooms and messages.
## Decision
SQLite with WAL (Write-Ahead Logging) for better concurrent read performance.
## Consequences
- Pro: Zero-config, async via aiosqlite, WAL allows concurrent readers
- Con: Single-writer bottleneck (acceptable for demo)
