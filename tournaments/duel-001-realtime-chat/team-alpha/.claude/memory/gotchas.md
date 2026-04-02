# Known Gotchas

## WebSocket
- FastAPI WebSocket.receive_json() raises WebSocketDisconnect on close — always wrap in try/except
- Broadcast must skip the sender to avoid echo (unless you want echo)
- starlette.websockets.WebSocketState must be checked before sending

## SQLite + aiosqlite
- aiosqlite connections are NOT thread-safe — one connection per operation or use connection pool
- WAL mode helps with concurrent reads: `PRAGMA journal_mode=WAL`
- Always use `async with` for connections to ensure cleanup

## Testing
- WebSocket tests in FastAPI use `with client.websocket_connect()` context manager
- Multiple WebSocket clients in same test need separate `websocket_connect()` calls
- Test database must be separate from production — use in-memory `:memory:`
