# Real-Time Chat — Team Alpha

WebSocket-based chat application with rooms, presence, and message persistence.

## Setup
```bash
pip install -e ".[dev]"
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

## API
### Rooms
- `POST /rooms` — Create room: `{"name": "general"}`
- `GET /rooms` — List all rooms
- `GET /rooms/:id` — Get room details
- `POST /rooms/:id/join?username=alice` — Join room
- `POST /rooms/:id/leave?username=alice` — Leave room

### Messages
- `GET /rooms/:id/messages?limit=50&offset=0` — Message history
- `GET /rooms/:id/messages/search?q=keyword` — Search messages

### Presence
- `GET /presence` — All online users
- `GET /rooms/:id/presence` — Room online users

### WebSocket
Connect: `ws://localhost:8000/ws?username=alice`
Send JSON messages with `type` field (see ARCHITECTURE.md).

## Tests
```bash
pytest tests/ -v
```
