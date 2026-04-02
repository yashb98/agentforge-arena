# Architecture Decisions Log

## 2026-04-02: SQLite with WAL mode
- Reason: WAL allows concurrent readers while writing, better for chat workload
- PRAGMA: journal_mode=WAL, busy_timeout=5000

## 2026-04-02: Service layer pattern (ChatService)
- Reason: Centralizes business logic, makes testing easier (mock service, not routes)
- Trade-off: Extra layer of indirection, but worth it for testability

## 2026-04-02: Pydantic for WebSocket message validation
- Reason: Type safety for incoming WS messages, clear error on invalid format
- Models: WSMessage (discriminated union on "type" field)

## 2026-04-02: Event-driven message handling
- Reason: Clean dispatch — each message type has its own handler function
- Pattern: ChatService.handle_event() → _handle_join(), _handle_message(), etc.
