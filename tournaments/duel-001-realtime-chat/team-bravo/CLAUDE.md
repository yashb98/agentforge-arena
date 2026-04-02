# Real-Time Chat — Team Bravo

> TDD-First approach. Tests define the contract, implementation follows.

## Stack
- **Backend:** Python 3.12, FastAPI, WebSockets, aiosqlite
- **Database:** SQLite (async via aiosqlite)
- **Testing:** pytest + pytest-asyncio + httpx

## Build Commands
```bash
pip install -e ".[dev]"
uvicorn src.main:app --host 0.0.0.0 --port 8000
pytest tests/ -v --tb=short
ruff check src/ tests/ --fix
```

## Architecture
- **Event-driven WebSocket** — messages as events with typed handlers
- **Service layer** — ChatService orchestrates rooms/messages/presence
- **SQLite with WAL mode** — better concurrent read performance
- **Dependency injection** — FastAPI Depends() for DB sessions

## Coding Patterns
- TDD: write test → see it fail → implement → see it pass → refactor
- Every public function has a test
- Pydantic strict models for WebSocket message validation
- Structured error responses with error codes

## What NOT To Do
- NEVER write implementation before the test exists
- NEVER use global mutable state without proper locking
- NEVER catch broad exceptions in WebSocket handlers
- NEVER skip error handling for WebSocket disconnect
