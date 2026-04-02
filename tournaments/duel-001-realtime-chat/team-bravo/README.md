# Real-Time Chat — Team Bravo

Event-driven WebSocket chat with TDD methodology.

## Setup
```bash
pip install -e ".[dev]"
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

## API Endpoints
### Rooms
- `POST /rooms` — `{"name": "general"}` → 201
- `GET /rooms` — List all rooms
- `GET /rooms/:id` — Room details + member count
- `POST /rooms/:id/join?username=X` — Join
- `POST /rooms/:id/leave?username=X` — Leave

### Messages
- `GET /rooms/:id/messages?limit=50&offset=0` — Paginated history
- `GET /rooms/:id/messages/search?q=keyword` — Search

### Presence
- `GET /presence` — All online users
- `GET /rooms/:id/presence` — Room presence

### WebSocket
`ws://localhost:8000/ws?username=alice`

## Run Tests
```bash
pytest tests/ -v
```

## Architecture
See ARCHITECTURE.md for full design. Key pattern: event-driven WebSocket dispatch.
