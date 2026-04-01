# Plan 1: Wire API Routes to Orchestrator

> Full spec — connects the FastAPI gateway to the tournament orchestrator, replacing inline stubs with proper route modules and initializing all services in the application lifespan.

## Problem Statement

`main.py` has two problems:
1. **Inline stub routes** (lines 145-210) return hardcoded empty responses — they duplicate and shadow the proper route modules in `routes/`.
2. **Services not initialized** — `TournamentOrchestrator`, `AgentTeamManager`, `JudgeService`, and `SandboxManager` are never created or stored on `app.state`, so the dependency providers in `dependencies.py` would fail at runtime.

The proper route modules (`tournaments.py`, `leaderboard.py`, `agents.py`, `challenges.py`) are already well-built with correct Pydantic response models and `Depends()` injection — they just aren't mounted.

## Architecture

```
FastAPI app (main.py)
  ├── lifespan: init Redis, DB, EventBus, SandboxManager, AgentTeamManager, JudgeService, Orchestrator
  ├── mount: routes/tournaments.router  (prefix /api/v1)
  ├── mount: routes/leaderboard.router  (already has /api/v1 prefix)
  ├── mount: routes/agents.router       (already has /api/v1/tournaments prefix)
  ├── mount: routes/challenges.router   (already has /api/v1 prefix)
  ├── mount: ws/spectator.router        (WebSocket)
  └── inline: /health (keep as-is)
```

## Changes Required

### Step 1: Update lifespan in `packages/api/src/main.py`

After EventBus init, create all service instances and store on `app.state`:

```python
# Sandbox Manager
from packages.sandbox.src.docker.manager import SandboxManager
app.state.sandbox_manager = SandboxManager(settings=settings)

# Agent Team Manager
from packages.agents.src.teams.manager import AgentTeamManager
app.state.agent_manager = AgentTeamManager(event_bus=app.state.event_bus)

# Judge Service
from packages.judge.src.scoring.service import JudgeService
app.state.judge_service = JudgeService(
    event_bus=app.state.event_bus,
    sandbox_manager=app.state.sandbox_manager,
)

# Tournament Orchestrator
from packages.core.src.tournament.orchestrator import TournamentOrchestrator
app.state.orchestrator = TournamentOrchestrator(
    event_bus=app.state.event_bus,
    sandbox_manager=app.state.sandbox_manager,
    agent_manager=app.state.agent_manager,
    judge_service=app.state.judge_service,
)
```

Add shutdown for agent manager:
```python
# In shutdown section
if hasattr(app.state, "agent_manager"):
    await app.state.agent_manager.teardown_all()
```

### Step 2: Replace inline stub routes with mounted routers

Remove all inline route definitions (lines 145-210) from `_register_routes()`. Replace with:

```python
from packages.api.src.routes.tournaments import router as tournaments_router
from packages.api.src.routes.leaderboard import router as leaderboard_router
from packages.api.src.routes.agents import router as agents_router
from packages.api.src.routes.challenges import router as challenges_router

def _register_routes(app: FastAPI) -> None:
    # Health check (keep inline)
    @app.get("/health", tags=["system"])
    async def health_check(request: Request) -> dict:
        # ... existing health check code ...

    # Mount route modules
    app.include_router(tournaments_router, prefix="/api/v1")
    app.include_router(leaderboard_router)   # already has /api/v1 prefix
    app.include_router(agents_router)        # already has /api/v1/tournaments prefix
    app.include_router(challenges_router)    # already has /api/v1 prefix
```

### Step 3: Fix prefix conflicts

The `tournaments.py` router has `prefix="/tournaments"`. When mounted with `/api/v1`, endpoints become `/api/v1/tournaments` — correct.

The `leaderboard.py` router has `prefix="/api/v1"` baked in — mount without additional prefix.

The `agents.py` router has `prefix="/api/v1/tournaments"` baked in — mount without additional prefix.

The `challenges.py` router has `prefix="/api/v1"` baked in — mount without additional prefix.

### Step 4: Type-annotate dependency providers in `dependencies.py`

```python
from packages.core.src.tournament.orchestrator import TournamentOrchestrator
from packages.agents.src.teams.manager import AgentTeamManager

def get_orchestrator(request: Request) -> TournamentOrchestrator:
    return request.app.state.orchestrator

def get_agent_manager(request: Request) -> AgentTeamManager:
    return request.app.state.agent_manager
```

### Step 5: Wire leaderboard to ELO calculator

Update `leaderboard.py` to accept a DB session dependency and query match results:

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from packages.api.src.dependencies import get_db_session
from packages.core.src.elo.calculator import compute_leaderboard

@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    db: AsyncSession = Depends(get_db_session),
) -> LeaderboardResponse:
    # Query match results from DB
    from packages.shared.src.db.models import MatchResultDB
    from sqlalchemy import select

    result = await db.execute(select(MatchResultDB))
    match_results = result.scalars().all()

    if not match_results:
        return LeaderboardResponse(entries=[], total=0, updated_at=datetime.utcnow())

    entries = compute_leaderboard(match_results)
    return LeaderboardResponse(entries=entries, total=len(entries), updated_at=datetime.utcnow())
```

**Note:** This requires `MatchResultDB` to exist in `packages/shared/src/db/models.py` — it already does.

### Step 6: Add cancel_tournament to orchestrator

The `tournaments.py` route calls `orchestrator.cancel_tournament()` but the orchestrator doesn't have this method. Add:

```python
async def cancel_tournament(self, tournament_id: UUID) -> Tournament:
    tournament = self._active_tournaments.get(tournament_id)
    if not tournament:
        raise ValueError(f"Tournament {tournament_id} not found")

    # Cancel phase timer
    if tournament_id in self._phase_timers:
        self._phase_timers[tournament_id].cancel()

    # Cancel health monitor
    if tournament_id in self._health_tasks:
        self._health_tasks[tournament_id].cancel()

    # Teardown sandboxes
    for team_id in tournament.team_ids:
        await self._sandbox.destroy_sandbox(str(team_id))

    tournament.current_phase = TournamentPhase.CANCELLED
    tournament.completed_at = datetime.utcnow()

    # Persist
    async with get_session() as session:
        await session.execute(
            TournamentDB.__table__.update()
            .where(TournamentDB.id == tournament_id)
            .values(current_phase="cancelled", updated_at=datetime.utcnow())
        )

    await self._events.publish(
        "tournament.cancelled",
        source="core.orchestrator",
        tournament_id=tournament_id,
        payload={},
    )

    return tournament
```

## Files Modified

| File | Action |
|------|--------|
| `packages/api/src/main.py` | Remove inline stubs, mount routers, init services in lifespan |
| `packages/api/src/dependencies.py` | Add type annotations, remove `# type: ignore` |
| `packages/api/src/routes/leaderboard.py` | Wire to DB + ELO calculator |
| `packages/core/src/tournament/orchestrator.py` | Add `cancel_tournament()` method |

## Files NOT Modified (already correct)

| File | Why |
|------|-----|
| `packages/api/src/routes/tournaments.py` | Already uses `Depends(get_orchestrator)`, fully typed |
| `packages/api/src/routes/agents.py` | Already uses both orchestrator + agent_manager deps |
| `packages/api/src/routes/challenges.py` | Self-contained filesystem-based loading, no deps needed |

## Testing Strategy

1. **Unit tests for dependency injection** — mock `app.state`, verify providers return correct types
2. **Integration test for route mounting** — create test app, verify all endpoints respond (not 404)
3. **Test tournament create → start → cancel flow** — full lifecycle via TestClient
4. **Test leaderboard with empty DB** — returns empty list
5. **Test leaderboard with mock match results** — returns ranked entries

### Test files to create/update:
- `packages/api/tests/test_main_routes.py` — Route mounting verification
- `packages/api/tests/test_tournament_routes.py` — Update existing tests for real orchestrator
- `packages/api/tests/test_leaderboard_routes.py` — Update for DB-backed leaderboard

## Acceptance Criteria

- [ ] `GET /health` returns `{"status": "healthy"}` with Redis + DB checks
- [ ] `POST /api/v1/tournaments` creates a tournament via orchestrator (returns 201)
- [ ] `GET /api/v1/tournaments` returns paginated list from orchestrator
- [ ] `GET /api/v1/tournaments/{id}` returns tournament or 404
- [ ] `POST /api/v1/tournaments/{id}/start` transitions PREP → RESEARCH
- [ ] `POST /api/v1/tournaments/{id}/cancel` cancels active tournament
- [ ] `GET /api/v1/leaderboard` returns entries from DB (empty if no matches)
- [ ] `GET /api/v1/tournaments/{id}/agents` returns agents via agent_manager
- [ ] `GET /api/v1/challenges` returns parsed challenges from filesystem
- [ ] All inline stubs removed from `main.py`
- [ ] All services initialized in lifespan and cleaned up on shutdown
- [ ] Type annotations on all dependency providers (no `# type: ignore`)
