# packages/shared — CLAUDE.md

## What This Package Is
Foundation layer for the entire monorepo. Contains shared types, database models,
event bus client, Redis client, Langfuse wrapper, configuration, and utilities.

**ZERO imports from other packages.** Everything else depends on `shared`.

## Key Modules
- `src/types/` — Pydantic models shared across packages (Tournament, Team, Agent, Match, Challenge)
- `src/db/` — SQLAlchemy async engine, session factory, base model, migrations
- `src/cache/` — Redis client wrapper with typed get/set/pub/sub
- `src/events/` — Event bus (Redis Streams) with publish/subscribe/consumer groups
- `src/tracing/` — Langfuse wrapper for LLM tracing
- `src/logger/` — Structured logging via structlog
- `src/config.py` — Pydantic Settings (all env vars)
- `src/errors/` — Custom exception hierarchy
- `src/constants/` — Enums, status codes, phase names

## Rules
- ALL models are Pydantic v2 `BaseModel`
- ALL database models use SQLAlchemy 2.0 `mapped_column`
- ALL functions are async
- NO business logic here — only infrastructure
