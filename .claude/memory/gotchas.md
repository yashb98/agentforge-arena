# AgentForge Arena — Known Gotchas

> Read this at the start of every session. These are hard-won lessons.

## 🔴 Critical Gotchas

### G001: Docker Sandbox network-deny doesn't block DNS
**Problem**: `--network-deny "*"` blocks HTTP but DNS resolution still works.
Agents can leak information via DNS queries.
**Workaround**: Use custom DNS resolver that only resolves whitelisted domains.
Configure in sandbox setup script.

### G002: Langfuse trace ingestion can lag under load
**Problem**: During BUILD phase with 10 agents all making LLM calls, Langfuse
ingestion queue can back up to 2000+ events. Traces appear delayed in dashboard.
**Workaround**: Use async batch ingestion with flush interval of 5s.
Don't rely on Langfuse for real-time spectator data — use Redis Pub/Sub directly.

### G003: LiteLLM proxy timeout vs model timeout
**Problem**: LiteLLM proxy has its own timeout (default 600s) independent of
the model's timeout. If LiteLLM times out first, you get a proxy error, not
a model error. Confusing error messages.
**Workaround**: Set LiteLLM timeout to 2x the model timeout.
Always catch both `litellm.Timeout` and `httpx.TimeoutException`.

### G004: Redis Pub/Sub messages are fire-and-forget
**Problem**: If a subscriber disconnects and reconnects, it misses messages
published during the gap. Spectators joining mid-tournament miss history.
**Workaround**: Use Redis Streams (not Pub/Sub) for events that must be replayed.
Use Pub/Sub only for real-time notifications where loss is acceptable.

### G005: Git worktrees share the .git directory
**Problem**: When using git worktrees for agent isolation, all worktrees share
the same .git directory. A `git gc` in one worktree affects all. Large repos
can cause lock contention.
**Workaround**: Use separate git repos per team, not worktrees. Copy challenge
files into each repo independently.

## 🟡 Important Gotchas

### G006: Pydantic v2 `model_dump()` doesn't round-trip datetimes
**Problem**: `model_dump(mode="json")` serializes datetimes to strings, but
`model_validate()` from those strings fails if the datetime field is annotated
as `datetime`, not `str`.
**Workaround**: Always use `model_dump(mode="json")` + `model_validate_json()`
for round-trip serialization. Or use `AwareDatetime` from Pydantic.

### G007: FastAPI dependency injection and async generators
**Problem**: Async generator dependencies (`yield` in `Depends()`) don't run
cleanup code if the request handler raises an exception in some edge cases.
**Workaround**: Use `contextlib.asynccontextmanager` instead of bare `yield`.
Always test cleanup paths.

### G008: SQLAlchemy async session and lazy loading
**Problem**: Lazy loading doesn't work with async sessions. Accessing a
relationship that wasn't eagerly loaded raises `MissingGreenlet`.
**Workaround**: Always use `selectinload()` or `joinedload()` in queries.
Never rely on lazy loading in async code.

### G009: Next.js 15 App Router + WebSocket
**Problem**: Next.js App Router doesn't natively support WebSocket upgrade.
Server Components can't hold WebSocket connections.
**Workaround**: Use a separate WebSocket endpoint via FastAPI (not Next.js).
Connect from client-side React components using `useEffect` + Socket.IO client.

### G010: Agent JSON mailbox file locking
**Problem**: Multiple agents reading/writing the same mailbox JSON file can
cause corruption under concurrent access.
**Workaround**: Use file locking (`fcntl.flock`) or use Redis lists as
mailboxes instead of JSON files for production.

## 🟢 Minor Gotchas

### G011: ruff and mypy disagree on import ordering
**Workaround**: Use ruff for both linting AND import sorting. Disable mypy's
import checker.

### G012: Docker Sandbox MicroVM cold start adds 2s
**Workaround**: Pre-warm sandboxes during PREP phase. Create sandboxes before
announcing the challenge to teams.

### G013: Langfuse Python SDK requires explicit flush
**Workaround**: Always call `langfuse.flush()` before process exit.
Use `atexit.register(langfuse.flush)` as a safety net.
