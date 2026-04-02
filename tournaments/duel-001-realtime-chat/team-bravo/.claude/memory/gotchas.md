# Known Gotchas

## FastAPI WebSocket Testing
- Use `with client.websocket_connect("/ws?username=test")` — username is query param
- Multiple WS clients in same test: each needs own `websocket_connect()` call
- WebSocket tests are synchronous in TestClient — use `receive_json()` not await

## aiosqlite
- Connection must be opened with `async with aiosqlite.connect(db_path)` 
- Row factory: set `conn.row_factory = aiosqlite.Row` for dict-like access
- Always commit after INSERT/UPDATE/DELETE

## Async Pitfalls
- `asyncio.gather(*tasks)` for parallel broadcasts — don't await sequentially
- WebSocketDisconnect can happen mid-send — always try/except around send_json
- Don't hold DB connection open during long WebSocket operations
