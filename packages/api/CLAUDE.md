# packages/api — CLAUDE.md

## What This Package Is
FastAPI REST/WebSocket API gateway. All external communication goes through here.

## Key Modules
- `src/main.py` — FastAPI app factory, lifespan, route registration
- `src/routes/tournaments.py` — Tournament CRUD + lifecycle endpoints
- `src/routes/leaderboard.py` — ELO leaderboard queries
- `src/routes/challenges.py` — Challenge library endpoints
- `src/routes/spectator.py` — WebSocket spectator connections
- `src/routes/replay.py` — Replay data endpoints
- `src/middleware/auth.py` — JWT authentication
- `src/middleware/rate_limit.py` — Rate limiting (Redis-based)
- `src/ws/handler.py` — WebSocket message routing

## API Versioning
All routes prefixed with `/api/v1/`. Breaking changes → new version.

## Dependencies
- `packages/shared` — Types, DB, events, config
- `packages/core` — Tournament orchestrator
- `packages/judge` — Judging invocation
- `packages/spectator` — WebSocket streaming
