# Design Spec: API Routes + Claude Code Agent Runtime

> **Date:** 2026-03-31
> **Status:** Approved
> **Scope:** packages/api (routes + DI) + packages/agents (Claude SDK runtime)

---

## 1. Overview

Two interconnected features:

1. **API Route Handlers** — Replace stub endpoints in `packages/api/src/main.py` with real route modules using FastAPI dependency injection, wired to the tournament orchestrator, DB, and event bus.

2. **Claude Code Agent Runtime** — Replace the TODO in `AgentProcess._process_message` with `claude_agent_sdk.ClaudeSDKClient` instances. Each agent role gets its own SDK client with role-specific tools, system prompt, and budget. Runs with `bypassPermissions` (sandbox is the security boundary).

---

## 2. Claude Code Agent Runtime

### 2.1 Architecture

```
TournamentOrchestrator.start_tournament()
  └─ AgentTeamManager.spawn_team()
       └─ For each agent_config in team:
            └─ ClaudeAgentRunner(
                 role=agent_config.role,
                 model=agent_config.model,
                 system_prompt=load_from(".claude/agents/{role}.md"),
                 tools=ROLE_TOOL_MAP[role],
                 cwd=f"/arena/team-{team_id}/project",
                 max_turns=agent_config.max_turns or 100,
                 max_budget_usd=per_agent_budget,
                 permission_mode="bypassPermissions",
               )
```

### 2.2 Role-to-Tool Mapping

| Role | Allowed Tools | Sandbox Access |
|------|--------------|----------------|
| Architect | Read, Write, Edit, Glob, Grep, Agent | Full |
| Builder | Read, Write, Edit, Bash, Glob, Grep | Full |
| Frontend | Read, Write, Edit, Bash, Glob, Grep | Full |
| Tester | Read, Write, Bash, Glob, Grep | Full |
| Critic | Read, Glob, Grep | Read-only |
| Researcher | Read, Write, WebSearch, WebFetch, Glob, Grep | Full + Network |

### 2.3 New Module: `packages/agents/src/runtime/claude_sdk.py`

```python
class ClaudeAgentRunner:
    """Wraps claude_agent_sdk.ClaudeSDKClient for a single agent role."""

    def __init__(
        self,
        agent: Agent,
        system_prompt: str,
        cwd: str,
        allowed_tools: list[str],
        event_bus: EventBus,
        max_turns: int = 100,
        max_budget_usd: float = 50.0,
        model: str | None = None,
    ) -> None: ...

    async def start(self) -> None:
        """Initialize the ClaudeSDKClient."""

    async def send_task(self, prompt: str) -> str:
        """Send a task prompt. Streams responses, publishes events, tracks cost.
        Returns the final result text."""

    async def stop(self) -> None:
        """Interrupt and cleanup the SDK client."""

    @property
    def is_responsive(self) -> bool:
        """Check if the agent has responded recently."""

    @property
    def total_cost_usd(self) -> float:
        """Accumulated cost from AssistantMessage.usage tracking."""

    @property
    def total_tokens(self) -> int:
        """Accumulated token usage."""
```

**Key implementation details:**

- Uses `ClaudeSDKClient` (not `query()`) for lifecycle control
- `permission_mode="bypassPermissions"` — safe because all execution happens inside Docker MicroVM sandbox
- `PostToolUse` hook publishes every tool action to Redis event bus:
  ```python
  async def on_tool_use(input_data, tool_use_id, context):
      await event_bus.publish(
          "agent.tool.used",
          source=f"agent.{agent.role.value}",
          tournament_id=agent.tournament_id,
          team_id=agent.team_id,
          agent_id=agent.id,
          payload={"tool": input_data.get("tool_name"), "input": input_data.get("tool_input")},
      )
      return {}
  ```
- Cost tracked per-agent from `AssistantMessage.usage` (input_tokens, output_tokens)
- Session resumption: capture `session_id` from `SystemMessage(subtype="init")`, use `resume=session_id` for follow-up tasks in same phase
- `setting_sources=["project"]` to load the team's project CLAUDE.md (the one created by `ProjectBootstrapper` inside the sandbox)

### 2.4 Changes to Existing Code

**`packages/agents/src/teams/manager.py`:**
- `AgentProcess` refactored to use `ClaudeAgentRunner` instead of the manual `_run_loop`
- `spawn_team()` creates `ClaudeAgentRunner` per agent config
- `check_team_health()` checks `runner.is_responsive`
- Remove `_read_inbox` / `_process_message` / `_mark_read` (SDK handles conversation)

**`packages/agents/src/communication/mailbox.py`:**
- Keep for orchestrator→agent task delivery (structured JSON messages)
- Agent-to-agent communication during build phase uses the mailbox
- `ClaudeAgentRunner.send_task()` converts mailbox messages to prompts

### 2.5 Phase-Specific Agent Behavior

| Phase | Who runs | What they do |
|-------|----------|-------------|
| RESEARCH | Researcher | `send_task("Read CHALLENGE.md. Research best practices, find relevant repos on GitHub, read docs.")` |
| ARCHITECTURE | Architect | `send_task("Read CHALLENGE.md and research notes. Create ARCHITECTURE.md, assign tasks to Builder/Frontend/Tester.")` |
| BUILD | Builder, Frontend, Tester (parallel) | Each gets tasks from Architect via mailbox. Builder: core logic. Frontend: UI. Tester: tests. |
| CROSS_REVIEW | Critic | `send_task("Review opponent code at /arena/team-X/opponent/. Write review in REVIEW.md.")` |
| FIX | Builder, Frontend | `send_task("Read REVIEW.md. Fix issues identified in cross-review.")` |

### 2.6 Budget & Guardrails

- Per-tournament budget: `TournamentConfig.budget_limit_usd` (default $500)
- Per-agent budget: tournament budget / (team_count * agents_per_team)
- `max_turns` per task: 100 (safety cap, not primary stop mechanism)
- `ClaudeAgentRunner` checks accumulated cost before each `send_task()` — refuses if over budget
- BudgetGate event published when any agent hits 80% of its allocation

---

## 3. API Routes

### 3.1 File Structure

```
packages/api/src/
├── main.py              (slim: app factory + router mounting only)
├── dependencies.py      (FastAPI Depends() providers)
├── routes/
│   ├── __init__.py
│   ├── tournaments.py   (tournament CRUD + lifecycle)
│   ├── agents.py        (agent status within tournaments)
│   ├── leaderboard.py   (ELO rankings)
│   └── challenges.py    (challenge library)
└── ws/
    ├── __init__.py
    └── spectator.py     (WebSocket real-time streaming)
```

### 3.2 Dependencies (`dependencies.py`)

```python
from fastapi import Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with get_session() as session:
        yield session

async def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus

async def get_orchestrator(request: Request) -> TournamentOrchestrator:
    return request.app.state.orchestrator

async def get_agent_manager(request: Request) -> AgentTeamManager:
    return request.app.state.agent_manager
```

Orchestrator, agent manager, and sandbox manager are initialized in `lifespan()` and stored on `app.state`.

### 3.3 Tournament Routes (`routes/tournaments.py`)

```
POST   /api/v1/tournaments              → create_tournament(config: TournamentConfig)
GET    /api/v1/tournaments               → list_tournaments(limit, offset, status_filter)
GET    /api/v1/tournaments/{id}          → get_tournament(id) — includes current_phase, teams, cost
POST   /api/v1/tournaments/{id}/start    → start_tournament(id) — provisions sandboxes, spawns agents
POST   /api/v1/tournaments/{id}/cancel   → cancel_tournament(id) — cleanup sandboxes, stop agents
GET    /api/v1/tournaments/{id}/events   → list_events(id, after_cursor) — paginated event log
```

**Response models (Pydantic):**
- `TournamentResponse` — id, format, current_phase, teams[], challenge_id, cost, timing
- `TournamentListResponse` — tournaments[], total, offset, limit

### 3.4 Agent Routes (`routes/agents.py`)

```
GET    /api/v1/tournaments/{id}/agents          → list_agents(tournament_id)
GET    /api/v1/tournaments/{id}/agents/{agent_id} → get_agent(agent_id) — status, cost, tokens, actions
GET    /api/v1/tournaments/{id}/teams/{team_id}/agents → list_team_agents(team_id)
```

**Response model:**
- `AgentResponse` — id, role, model, status, total_tokens, total_cost_usd, actions_count, errors_count, last_heartbeat

### 3.5 Leaderboard Routes (`routes/leaderboard.py`)

```
GET    /api/v1/leaderboard                      → get_leaderboard(category, limit)
GET    /api/v1/leaderboard/{config_name}/history → get_rating_history(config_name)
```

**Response model:**
- `LeaderboardResponse` — entries[] (team_config_name, elo_rating, elo_ci_lower, elo_ci_upper, wins, losses, draws, win_rate, avg_score)

### 3.6 Challenge Routes (`routes/challenges.py`)

```
GET    /api/v1/challenges                       → list_challenges(category, difficulty)
GET    /api/v1/challenges/{id}                  → get_challenge(id)
POST   /api/v1/challenges                       → create_challenge(challenge: Challenge) — admin only
```

**Challenges loaded from:** `challenges/library/*/CHALLENGE.md` (parsed on startup, cached in memory)

### 3.7 WebSocket Spectator (`ws/spectator.py`)

```
WS     /ws/spectate/{tournament_id}             → real-time event stream
```

**Implementation:**
- On connect: subscribe to Redis event bus for `tournament.{id}.*` and `agent.tool.*` events
- Stream events as JSON to WebSocket client
- Include: phase changes, agent tool uses, agent status changes, budget warnings, completion
- Heartbeat ping every 30s to detect stale connections

### 3.8 Changes to `main.py`

- Remove all inline route handlers (move to route modules)
- Keep: `lifespan()`, `create_app()`, health check
- Add to `lifespan()`:
  - Initialize `SandboxManager`, `AgentTeamManager`, `TournamentOrchestrator`
  - Store on `app.state` for dependency injection
- Mount routers:
  ```python
  from packages.api.src.routes import tournaments, agents, leaderboard, challenges
  from packages.api.src.ws import spectator

  app.include_router(tournaments.router, prefix="/api/v1", tags=["tournaments"])
  app.include_router(agents.router, prefix="/api/v1", tags=["agents"])
  app.include_router(leaderboard.router, prefix="/api/v1", tags=["leaderboard"])
  app.include_router(challenges.router, prefix="/api/v1", tags=["challenges"])
  app.include_router(spectator.router, tags=["spectator"])
  ```

### 3.9 Response Models (`packages/shared/src/types/responses.py`)

New file for API response models (separate from domain models):

```python
class TournamentResponse(BaseModel):
    id: UUID
    format: TournamentFormat
    current_phase: TournamentPhase
    challenge_id: str
    teams: list[TeamSummary]
    total_cost_usd: float
    started_at: datetime | None
    completed_at: datetime | None
    winner_team_id: UUID | None

class TeamSummary(BaseModel):
    id: UUID
    name: str
    agent_count: int
    total_cost_usd: float

class AgentResponse(BaseModel):
    id: UUID
    team_id: UUID
    role: AgentRole
    model: ModelProvider
    status: AgentStatus
    total_tokens_used: int
    total_cost_usd: float
    actions_count: int
    errors_count: int
    last_heartbeat: datetime | None

class LeaderboardResponse(BaseModel):
    entries: list[LeaderboardEntry]
    total: int
    updated_at: datetime
```

---

## 4. New Dependencies

Add to `pyproject.toml`:
```
claude-agent-sdk>=0.1.0
```

---

## 5. Testing Strategy

### Agent Runtime Tests (`packages/agents/tests/`)
- Unit: Mock `ClaudeSDKClient`, verify `ClaudeAgentRunner` sends correct options (tools, cwd, prompt)
- Unit: Verify cost tracking accumulates from `AssistantMessage.usage`
- Unit: Verify PostToolUse hook publishes events to bus
- Unit: Verify budget check refuses task when over limit
- Integration: Spawn a real SDK client in a temp directory, run a simple task

### API Route Tests (`packages/api/tests/`)
- Unit: Each route with mocked dependencies (orchestrator, DB, event bus)
- Unit: Validate request/response Pydantic models
- Unit: Error cases (tournament not found, invalid config, budget exceeded)
- Integration: Full create→start→list flow with real DB

---

## 6. Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `packages/agents/src/runtime/__init__.py` | Package init |
| `packages/agents/src/runtime/claude_sdk.py` | ClaudeAgentRunner |
| `packages/api/src/dependencies.py` | FastAPI DI providers |
| `packages/api/src/routes/__init__.py` | Package init |
| `packages/api/src/routes/tournaments.py` | Tournament CRUD + lifecycle |
| `packages/api/src/routes/agents.py` | Agent status endpoints |
| `packages/api/src/routes/leaderboard.py` | ELO leaderboard |
| `packages/api/src/routes/challenges.py` | Challenge library |
| `packages/api/src/ws/__init__.py` | Package init |
| `packages/api/src/ws/spectator.py` | WebSocket spectator |
| `packages/shared/src/types/responses.py` | API response models |

### Modified Files
| File | Change |
|------|--------|
| `packages/agents/src/teams/manager.py` | Replace AgentProcess with ClaudeAgentRunner |
| `packages/api/src/main.py` | Slim down, mount routers, init services in lifespan |
| `pyproject.toml` | Add claude-agent-sdk dependency |

### Not Modified
| File | Why |
|------|-----|
| `packages/agents/src/self_config/bootstrap.py` | Still used — Architect agent calls this to scaffold projects |
| `packages/agents/src/communication/mailbox.py` | Still used — orchestrator→agent task delivery |
| `packages/core/src/tournament/orchestrator.py` | No changes — API routes call it via DI |
| `packages/shared/src/types/models.py` | No changes — domain models stay as-is |
