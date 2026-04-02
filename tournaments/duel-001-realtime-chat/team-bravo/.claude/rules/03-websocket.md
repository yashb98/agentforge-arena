# WebSocket Rules
- All WS messages validated through Pydantic before processing
- Message types: join_room, leave_room, send_message, typing, dm, system
- Disconnect handling: always clean up presence + notify room
- Never await send on a potentially closed connection without guard
- Room isolation: messages MUST NOT leak between rooms
