# Plan 4: Wire AgentProcess to RedisMailbox

> Full spec — replaces file-based JSON inbox in AgentProcess with the existing RedisMailbox implementation, making inter-agent communication atomic and production-ready.

## Problem Statement

`AgentProcess` in `manager.py` uses file-based JSON inbox:
- `_read_inbox()` reads from `{inbox_path}/{role}.json`
- `send_message()` writes to `{inbox_path}/{role}.json`
- `_mark_read()` modifies the JSON file in place

This is fragile (Gotcha G010: no file locking, race conditions with concurrent agents).

Meanwhile, `RedisMailbox` in `communication/mailbox.py` already exists with:
- `send()` — atomic LPUSH to Redis list
- `receive()` — blocking BRPOP (destructive read, no "mark as read" needed)
- `receive_all()` — non-blocking drain of all pending messages
- `peek()`, `inbox_size()`, `clear_inbox()`, `clear_team()`

The fix is straightforward: inject `RedisMailbox` into `AgentProcess` and replace file I/O with Redis calls.

## Architecture

```
Before:
  AgentProcess → filesystem JSON files → AgentProcess
  (race conditions, no locking, breaks under concurrent access)

After:
  AgentProcess → RedisMailbox → Redis LPUSH/BRPOP → RedisMailbox → AgentProcess
  (atomic, reliable, supports blocking wait)
```

## Changes Required

### Step 1: Update `AgentProcess.__init__()` to accept `RedisMailbox`

```python
class AgentProcess:
    def __init__(
        self,
        agent: Agent,
        system_prompt: str,
        workspace_path: str,
        mailbox: RedisMailbox,
        llm_client: object | None = None,  # Added in Plan 2
    ) -> None:
        self.agent = agent
        self.system_prompt = system_prompt
        self.workspace_path = workspace_path
        self._mailbox = mailbox
        self._llm = llm_client
        self._task: asyncio.Task | None = None
```

Remove:
- `inbox_path` parameter
- `self.inbox_path` attribute

### Step 2: Replace `_read_inbox()` with `RedisMailbox.receive_all()`

```python
async def _read_inbox(self) -> list[AgentMessage]:
    """Read all pending messages from Redis mailbox."""
    return await self._mailbox.receive_all(self.agent.role)
```

This replaces 12 lines of file I/O + JSON parsing with a single Redis call.

### Step 3: Replace `send_message()` with `RedisMailbox.send()`

```python
async def send_message(self, message: AgentMessage) -> None:
    """Send a message via Redis mailbox."""
    await self._mailbox.send(message)
```

This replaces 13 lines of file I/O + JSON serialization.

### Step 4: Remove `_mark_read()`

Delete entirely. `RedisMailbox.receive_all()` uses RPOP which is destructive — messages are removed on read. No separate "mark as read" step needed.

### Step 5: Update `_run_loop()` to use blocking receive (optional optimization)

Instead of polling with `asyncio.sleep(2)`, we can use blocking BRPOP:

```python
async def _run_loop(self) -> None:
    """Main agent loop: wait for messages, process them."""
    while self.agent.status not in (AgentStatus.TERMINATED, AgentStatus.ERROR):
        try:
            # Blocking wait for next message (5s timeout for heartbeat updates)
            message = await self._mailbox.receive(self.agent.role, timeout=5.0)

            if message is not None:
                await self._process_message(message)

            # Update heartbeat regardless
            self.agent.last_heartbeat = datetime.utcnow()

        except asyncio.CancelledError:
            self.agent.status = AgentStatus.TERMINATED
            break
        except Exception:
            self.agent.errors_count += 1
            logger.exception("Agent %s error", self.agent.role.value)
            if self.agent.errors_count >= 10:
                self.agent.status = AgentStatus.ERROR
                break
            await asyncio.sleep(5)
```

This is more efficient than polling — agents block on Redis instead of sleeping.

### Step 6: Update `AgentTeamManager.spawn_team()` to create `RedisMailbox`

```python
async def spawn_team(
    self,
    team_id: UUID,
    tournament_id: UUID,
    config: TeamConfig,
    sandbox_id: str,
    redis: aioredis.Redis,  # New parameter
    llm_client: object | None = None,  # From Plan 2
) -> list[UUID]:
    """Spawn all agents for a team."""
    settings = get_settings()
    workspace_path = f"{settings.sandbox.workspace_base}/team-{team_id}/project"

    # Create shared mailbox for this team
    mailbox = RedisMailbox(redis=redis, team_id=team_id)

    agents: list[AgentProcess] = []
    agent_ids: list[UUID] = []

    for agent_config in config.agents:
        agent = Agent(
            id=uuid4(),
            team_id=team_id,
            tournament_id=tournament_id,
            role=agent_config.role,
            model=agent_config.model,
        )

        # Load system prompt
        prompt_file = AGENT_PROMPT_FILES.get(agent_config.role, "")
        system_prompt = ""
        try:
            system_prompt = Path(prompt_file).read_text()
        except FileNotFoundError:
            logger.warning("System prompt not found: %s", prompt_file)
            system_prompt = f"You are the {agent_config.role.value} agent."

        process = AgentProcess(
            agent=agent,
            system_prompt=system_prompt,
            workspace_path=workspace_path,
            mailbox=mailbox,
            llm_client=llm_client,
        )

        await process.start()
        agents.append(process)
        agent_ids.append(agent.id)

    self._teams[team_id] = agents
    self._mailboxes[team_id] = mailbox  # Store for cleanup
    logger.info("Spawned %d agents for team %s", len(agents), team_id)
    return agent_ids
```

### Step 7: Update `AgentTeamManager.__init__()` to track mailboxes

```python
class AgentTeamManager:
    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus
        self._teams: dict[UUID, list[AgentProcess]] = {}
        self._mailboxes: dict[UUID, RedisMailbox] = {}
```

### Step 8: Update `teardown_team()` to clear Redis mailboxes

```python
async def teardown_team(self, team_id: UUID) -> None:
    """Stop all agents and clean up Redis mailboxes."""
    agents = self._teams.get(team_id, [])
    for ap in agents:
        await ap.stop()

    # Clear Redis mailboxes
    mailbox = self._mailboxes.get(team_id)
    if mailbox:
        await mailbox.clear_team()
        del self._mailboxes[team_id]

    if team_id in self._teams:
        del self._teams[team_id]

    logger.info("Team %s torn down (agents + mailboxes)", team_id)
```

### Step 9: Update imports in `manager.py`

Add:
```python
import redis.asyncio as aioredis
from packages.agents.src.communication.mailbox import RedisMailbox
```

Remove:
```python
# No longer needed:
import orjson  # Was used for JSON file I/O
```

### Step 10: Update orchestrator to pass Redis to agent manager

In `start_tournament()`, the orchestrator calls `self._agents.spawn_team()`. It needs to pass the Redis instance. Two approaches:

**Approach A (recommended):** Store Redis on the AgentTeamManager at init time:
```python
class AgentTeamManager:
    def __init__(self, event_bus: EventBus, redis: aioredis.Redis) -> None:
        self._events = event_bus
        self._redis = redis
        self._teams: dict[UUID, list[AgentProcess]] = {}
        self._mailboxes: dict[UUID, RedisMailbox] = {}
```

Then `spawn_team()` uses `self._redis` internally — no change to the orchestrator's call site.

**Approach B:** Pass Redis per call. More flexible but more verbose.

Go with **Approach A** — Redis is a long-lived connection, not per-request.

## Files Modified

| File | Change |
|------|--------|
| `packages/agents/src/teams/manager.py` | Replace file I/O with RedisMailbox, accept Redis in constructor |
| `packages/agents/src/communication/mailbox.py` | No changes needed (already complete) |

## Files NOT Modified

| File | Why |
|------|-----|
| `packages/agents/src/communication/mailbox.py` | Already fully implemented with Redis |
| `packages/core/src/tournament/orchestrator.py` | No changes if using Approach A |

## Dependencies

- **Depends on Plan 1** — `AgentTeamManager` must be initialized in lifespan with Redis
- Redis must be running (docker-compose already provides it)
- `orjson` still needed by `RedisMailbox` (for JSON serialization to Redis)

## Testing Strategy

1. **Unit test RedisMailbox** — use `fakeredis` to test send/receive/broadcast/peek/clear
2. **Unit test AgentProcess with Redis** — mock RedisMailbox, verify `_read_inbox` calls `receive_all()`
3. **Integration test** — spawn 2 agents, send message from one, verify other receives it via Redis
4. **Test teardown** — verify `clear_team()` removes all Redis keys for the team

### Test files:
- `packages/agents/tests/test_redis_mailbox.py`
- `packages/agents/tests/test_agent_process.py` (update existing)

## Acceptance Criteria

- [ ] `AgentProcess` no longer reads/writes JSON files
- [ ] `AgentProcess._read_inbox()` calls `RedisMailbox.receive_all()`
- [ ] `AgentProcess.send_message()` calls `RedisMailbox.send()`
- [ ] `_mark_read()` method is removed (RPOP is destructive)
- [ ] `_run_loop()` uses blocking `receive()` instead of `sleep(2)` polling
- [ ] `AgentTeamManager` creates `RedisMailbox` per team during `spawn_team()`
- [ ] `teardown_team()` clears Redis mailboxes via `clear_team()`
- [ ] No file-based inbox paths in `AgentProcess` or `AgentTeamManager`
- [ ] All agents in a team share the same `RedisMailbox` instance
- [ ] `inbox_path` parameter is removed from all constructors
