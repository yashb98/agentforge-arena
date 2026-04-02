---
name: websocket-chat
display_name: "WebSocket Chat Patterns"
category: project
---
# WebSocket Chat Skill
## Connection Lifecycle
1. Client connects to /ws?username=X
2. Server registers connection in ConnectionManager
3. Client sends JSON messages with type field
4. Server broadcasts to room members
5. On disconnect, server cleans up presence and notifies room

## Message Types
- `join_room` — Join a chat room
- `leave_room` — Leave a chat room  
- `send_message` — Send message to current room
- `typing` — Typing indicator
- `dm` — Direct/private message

## Anti-Patterns
- Don't store WebSocket objects in DB
- Don't use sync broadcast (use asyncio.gather)
- Don't forget to handle disconnects gracefully
