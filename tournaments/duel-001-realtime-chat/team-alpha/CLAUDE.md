# Real-Time Chat — Team Alpha

> Architecture-First approach. Design the system completely before coding.

## Stack
- **Backend:** Python 3.12, FastAPI, WebSockets, aiosqlite
- **Database:** SQLite (async via aiosqlite)
- **Testing:** pytest + pytest-asyncio + httpx

## Build Commands
```bash
pip install -e ".[dev]"
uvicorn src.main:app --host 0.0.0.0 --port 8000
pytest tests/ -v
ruff check src/ tests/
```

## Architecture
- **ConnectionManager** — singleton managing all WebSocket connections per room
- **Repository pattern** — database access isolated in rooms.py, messages.py
- **In-memory presence** — dict-based tracker, not persisted (ephemeral by nature)
- **Lifespan** — DB init on startup, cleanup on shutdown

## Coding Patterns
- Async everywhere — no sync DB calls
- Pydantic models for all API I/O
- WebSocket JSON protocol: `{"type": "...", "data": {...}}`
- All errors return proper HTTP status codes with detail messages

## What NOT To Do
- NEVER use sync sqlite3 — always aiosqlite
- NEVER store WebSocket connections in the database
- NEVER broadcast to disconnected clients without try/except
- NEVER skip type hints or docstrings on public functions
