# ADR-002: Event-Driven Connection Manager

## Status: Accepted
## Context
Need to handle different WebSocket message types cleanly.
## Decision
Handler registry pattern — each message type maps to an async handler function.
## Consequences
- Pro: Clean separation, each handler testable independently, easy to add new types
- Con: Slight indirection vs simple if/elif
