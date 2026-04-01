# Challenge: Real-Time Chat Application

## Difficulty: Hard | Category: Real Time | Time: 120 minutes

## Brief

Build a real-time chat application with rooms, message persistence, and user presence.
The app should support multiple concurrent users communicating via WebSockets with
a clean REST API for room and message management.

## Requirements

### Functional (Must Have)
1. **WebSocket Connection** — Clients connect via WebSocket at `/ws` with a username
2. **Chat Rooms** — Create, join, and leave named rooms via REST API
3. **Message Sending** — Send messages to rooms; all members receive them in real-time
4. **Message History** — GET endpoint returning past messages with pagination (limit/offset)
5. **User Presence** — Show which users are currently online in each room

### Non-Functional (Should Have)
6. **Typing Indicators** — Broadcast when a user starts/stops typing
7. **Message Search** — Search messages by keyword within a room
8. **Room Listing** — List all active rooms with member counts
9. **Private Messages** — Direct messages between two users

### Bonus (Nice to Have)
10. **Message Reactions** — React to messages with emoji
11. **File Sharing** — Share files/images in chat
12. **Read Receipts** — Track which messages a user has read

## Tech Constraints
- Backend: Python (FastAPI + websockets) or Node.js (Express + ws/Socket.io)
- Database: PostgreSQL, SQLite, or Redis for persistence
- Must include a Dockerfile
- Must include a README with setup instructions
- Must include an ARCHITECTURE.md

## Hidden Test Suite Hints
- Tests will connect multiple WebSocket clients simultaneously
- Tests verify message ordering and delivery guarantees
- Tests check room isolation (messages don't leak between rooms)
- Tests verify persistence (messages survive reconnection)
- Tests check presence accuracy after connect/disconnect
- The test suite expects your app to run on port 8000

## Scoring Weights
| Dimension | Weight |
|-----------|--------|
| Functionality | 0.35 |
| Code Quality | 0.15 |
| Test Coverage | 0.15 |
| UX/Design | 0.10 |
| Architecture | 0.15 |
| Innovation | 0.10 |
