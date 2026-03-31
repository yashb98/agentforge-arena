# Rule 04: Architecture Patterns

## Applies To
All backend packages. Frontend has its own patterns in `packages/web/CLAUDE.md`.

## Core Pattern: Event-Driven + CQRS

### Event Bus (Redis Streams)
Every state change publishes an event. Events are the source of truth.

```python
# Event structure — ALL events follow this shape
class ArenaEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str          # "tournament.match.started"
    timestamp: datetime      # UTC always
    version: int = 1         # Schema version for evolution
    source: str              # "core.tournament_orchestrator"
    correlation_id: str      # Links related events across services
    payload: dict            # Event-specific data

# Publishing
await event_bus.publish("tournament.match.started", payload={...})

# Subscribing
@event_bus.subscribe("tournament.match.*")
async def handle_match_event(event: ArenaEvent): ...
```

### CQRS Split
- **Commands** (writes): Go through service layer → validate → execute → publish event
- **Queries** (reads): Go directly to read-optimized views (materialized views, Redis cache)
- **Projections**: Event handlers that build read models from events

## Service Layer Pattern
```python
# Every package exposes services, not raw DB access
class TournamentService:
    def __init__(self, db: AsyncSession, event_bus: EventBus, sandbox_mgr: SandboxManager):
        self._db = db
        self._events = event_bus
        self._sandbox = sandbox_mgr

    async def start_tournament(self, config: TournamentConfig) -> Tournament:
        # 1. Validate
        # 2. Create DB records
        # 3. Provision sandboxes
        # 4. Publish event
        # 5. Return result
```

## Repository Pattern for DB Access
```python
class TournamentRepository:
    """Encapsulates all tournament DB queries. No raw SQL outside repos."""

    async def get_by_id(self, id: UUID) -> Tournament | None: ...
    async def list_active(self, limit: int = 50) -> list[Tournament]: ...
    async def create(self, data: TournamentCreate) -> Tournament: ...
    async def update_phase(self, id: UUID, phase: TournamentPhase) -> None: ...
```

## Dependency Injection
- Use `Depends()` in FastAPI for request-scoped dependencies
- Use constructor injection in services
- Define interfaces (Protocol classes) for all external dependencies
- Wire in `packages/api/src/dependencies.py`

## Database Patterns
- SQLAlchemy 2.0 async ORM with `mapped_column`
- Alembic for migrations (auto-generate, then review)
- UUID primary keys everywhere
- `created_at` and `updated_at` on every table
- Soft deletes (`deleted_at`) for user-facing entities
- Indexes on every foreign key and every field used in WHERE clauses

## Async Patterns
- `asyncio` everywhere — no sync code in the hot path
- Use `asyncio.TaskGroup` for parallel operations (Python 3.11+)
- Use `asyncio.Semaphore` for rate limiting concurrent operations
- NEVER use `asyncio.sleep()` as a synchronization mechanism — use events/conditions
- Cancel tasks cleanly with `task.cancel()` + try/except CancelledError

## Error Recovery
- **Retry with exponential backoff** for transient failures (network, DB connections)
- **Circuit breaker** for external services (LLM providers, GitHub API)
- **Dead letter queue** for events that fail processing 3 times
- **Saga pattern** for multi-step operations (tournament creation → sandbox provisioning → agent spawning)
