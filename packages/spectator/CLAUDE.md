# packages/spectator — CLAUDE.md

## What This Package Is
Real-time spectator system. Streams agent actions, code changes, and tutor
commentary to observers via WebSocket.

## Key Modules
- `src/websocket/server.py` — Socket.IO server for real-time streaming
- `src/tutor/commentator.py` — AI commentary engine (Haiku 4.5)
- `src/terminal/streamer.py` — xterm.js terminal output streaming
- `src/code_viewer/differ.py` — Monaco editor code diff streaming
- `src/dashboard/state.py` — Dashboard state aggregation

## Real-Time Pipeline
```
Agent Action → Redis Pub/Sub → WebSocket Server → Browser Client
                    ↓
              Tutor AI → Commentary → WebSocket → Browser
```

## Latency Target: <100ms from agent action to spectator screen

## Dependencies
- `packages/shared` — Types, events, config
