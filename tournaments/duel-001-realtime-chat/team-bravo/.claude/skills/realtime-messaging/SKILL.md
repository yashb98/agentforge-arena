---
name: realtime-messaging
display_name: "Real-Time Messaging Patterns"
category: project
---
# Real-Time Messaging Skill
## Event-Driven Architecture
Messages flow as typed events through a central ChatService:
1. WebSocket receives raw JSON
2. Validate with Pydantic into typed event
3. ChatService.handle_event() dispatches to correct handler
4. Handler executes business logic + persistence
5. ChatService broadcasts response to relevant connections

## Testing Real-Time Systems
- Test message ordering (timestamps must be monotonic)
- Test room isolation (connect 2 clients to different rooms, verify no leakage)
- Test reconnection (disconnect + reconnect, verify history available)
- Test concurrent sends (multiple clients sending simultaneously)
