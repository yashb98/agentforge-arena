# ADR-003: Typed JSON WebSocket Protocol

## Status: Accepted
## Context
Need a structured protocol for WebSocket messages.
## Decision
JSON with `type` discriminator field. Pydantic models for each message type.
## Consequences
- Pro: Type-safe, self-documenting, validatable
- Con: Slightly more verbose than ad-hoc JSON
