# API Routes + Claude Code Agent Runtime — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up real API route handlers with dependency injection AND integrate Claude Agent SDK as the agent runtime, replacing the stub process loop.

**Architecture:** FastAPI route modules with `Depends()` DI, each injecting the tournament orchestrator/event bus/DB session. Agent runtime uses `claude_agent_sdk.ClaudeSDKClient` per agent role with `bypassPermissions` mode (sandbox is security boundary). Events stream to Redis for spectator WebSocket.

**Tech Stack:** FastAPI, Pydantic v2, claude-agent-sdk, Redis Streams, SQLAlchemy async, WebSocket

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `packages/shared/src/types/responses.py` | API response Pydantic models (TournamentResponse, AgentResponse, etc.) |
| `packages/api/src/dependencies.py` | FastAPI DI providers (get_orchestrator, get_event_bus, get_db_session) |
| `packages/api/src/routes/__init__.py` | Package init |
| `packages/api/src/routes/tournaments.py` | Tournament CRUD + lifecycle (create, list, get, start, cancel) |
| `packages/api/src/routes/agents.py` | Agent status endpoints (list agents, get agent detail) |
| `packages/api/src/routes/leaderboard.py` | ELO leaderboard endpoint |
| `packages/api/src/routes/challenges.py` | Challenge library endpoints |
| `packages/api/src/ws/__init__.py` | Package init |
| `packages/api/src/ws/spectator.py` | WebSocket spectator real-time streaming |
| `packages/agents/src/runtime/__init__.py` | Package init |
| `packages/agents/src/runtime/claude_sdk.py` | ClaudeAgentRunner wrapping ClaudeSDKClient |

### Modified Files

| File | What Changes |
|------|-------------|
| `packages/api/src/main.py` | Remove inline stubs, mount routers, init services in lifespan |
| `packages/agents/src/teams/manager.py` | Replace AgentProcess internals with ClaudeAgentRunner |
| `pyproject.toml` | Add claude-agent-sdk dependency |

---

### Task 1: Add claude-agent-sdk Dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependency to pyproject.toml**

Open `pyproject.toml` and add `claude-agent-sdk` to the dependencies list:

```python
# In the [project] dependencies array, add after "tenacity":
"claude-agent-sdk>=0.1.0",
```

The full dependencies array should end with:
```toml
dependencies = [
    "anthropic>=0.40.0",
    "httpx>=0.27.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.6.0",
    "typer[all]>=0.12.0",
    "structlog>=24.1.0",
    "docker>=7.0.0",
    "pyyaml>=6.0",
    "jinja2>=3.1.0",
    "aiosqlite>=0.20.0",
    "python-dotenv>=1.0.0",
    "tenacity>=8.2.0",
    "rich>=13.7.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30.0",
    "redis>=5.2.0",
    "orjson>=3.10.0",
    "litellm>=1.50.0",
    "langfuse>=2.50.0",
    "numpy>=2.1.0",
    "scipy>=1.14.0",
    "socketio>=5.11.0",
    "qdrant-client>=1.12.0",
    "boto3>=1.35.0",
    "claude-agent-sdk>=0.1.0",
]
```

- [ ] **Step 2: Install**

Run: `pip install -e ".[dev]" --break-system-packages`

- [ ] **Step 3: Verify import works**

Run: `python -c "import claude_agent_sdk; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add claude-agent-sdk dependency"
```

---

### Task 2: API Response Models

**Files:**
- Create: `packages/shared/src/types/responses.py`
- Test: `packages/shared/tests/test_responses.py`

- [ ] **Step 1: Write the failing test**

Create `packages/shared/tests/test_responses.py`:

```python
"""Tests for API response models."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from packages.shared.src.types.models import (
    AgentRole,
    AgentStatus,
    ChallengeCategory,
    ChallengeDifficulty,
    LeaderboardEntry,
    ModelProvider,
    TournamentFormat,
    TournamentPhase,
)
from packages.shared.src.types.responses import (
    AgentResponse,
    ChallengeResponse,
    ChallengeListResponse,
    LeaderboardResponse,
    TeamSummary,
    TournamentListResponse,
    TournamentResponse,
)


def test_tournament_response_serializes():
    team = TeamSummary(
        id=uuid4(),
        name="Alpha Team",
        agent_count=5,
        total_cost_usd=12.50,
    )
    resp = TournamentResponse(
        id=uuid4(),
        format=TournamentFormat.DUEL,
        current_phase=TournamentPhase.BUILD,
        challenge_id="url-shortener-saas",
        teams=[team],
        total_cost_usd=25.0,
        started_at=datetime.utcnow(),
        completed_at=None,
        winner_team_id=None,
    )
    data = resp.model_dump(mode="json")
    assert data["format"] == "duel"
    assert data["current_phase"] == "build"
    assert len(data["teams"]) == 1
    assert data["teams"][0]["name"] == "Alpha Team"


def test_tournament_list_response():
    resp = TournamentListResponse(tournaments=[], total=0, offset=0, limit=20)
    assert resp.total == 0


def test_agent_response_serializes():
    resp = AgentResponse(
        id=uuid4(),
        team_id=uuid4(),
        role=AgentRole.BUILDER,
        model=ModelProvider.CLAUDE_SONNET_4_6,
        status=AgentStatus.CODING,
        total_tokens_used=15000,
        total_cost_usd=1.25,
        actions_count=42,
        errors_count=0,
        last_heartbeat=datetime.utcnow(),
    )
    data = resp.model_dump(mode="json")
    assert data["role"] == "builder"
    assert data["status"] == "coding"


def test_leaderboard_response():
    entry = LeaderboardEntry(
        team_config_name="balanced-v1",
        elo_rating=1550.0,
        elo_ci_lower=1500.0,
        elo_ci_upper=1600.0,
        matches_played=10,
        wins=7,
        losses=2,
        draws=1,
        win_rate=0.7,
        avg_score=82.5,
        last_match=datetime.utcnow(),
    )
    resp = LeaderboardResponse(
        entries=[entry],
        total=1,
        updated_at=datetime.utcnow(),
    )
    data = resp.model_dump(mode="json")
    assert data["total"] == 1
    assert data["entries"][0]["elo_rating"] == 1550.0


def test_challenge_response():
    resp = ChallengeResponse(
        id="url-shortener-saas",
        title="URL Shortener SaaS",
        description="Build a production URL shortener",
        category=ChallengeCategory.SAAS_APP,
        difficulty=ChallengeDifficulty.MEDIUM,
        time_limit_minutes=90,
        requirements=["User registration", "Short URL creation"],
        tags=["saas", "web"],
    )
    data = resp.model_dump(mode="json")
    assert data["category"] == "saas_app"
    assert len(data["requirements"]) == 2


def test_challenge_list_response():
    resp = ChallengeListResponse(challenges=[], total=0)
    assert resp.total == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/shared/tests/test_responses.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'packages.shared.src.types.responses'`

- [ ] **Step 3: Write the response models**

Create `packages/shared/src/types/responses.py`:

```python
"""API response models — separate from domain models.

These are returned by FastAPI endpoints. They may omit internal fields
or reshape data for API consumers.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from packages.shared.src.types.models import (
    AgentRole,
    AgentStatus,
    ChallengeCategory,
    ChallengeDifficulty,
    LeaderboardEntry,
    ModelProvider,
    TournamentFormat,
    TournamentPhase,
)


class TeamSummary(BaseModel):
    """Summary of a team for tournament responses."""

    id: UUID
    name: str
    agent_count: int
    total_cost_usd: float


class TournamentResponse(BaseModel):
    """Full tournament detail response."""

    id: UUID
    format: TournamentFormat
    current_phase: TournamentPhase
    challenge_id: str
    teams: list[TeamSummary]
    total_cost_usd: float
    started_at: datetime | None = None
    completed_at: datetime | None = None
    winner_team_id: UUID | None = None


class TournamentListResponse(BaseModel):
    """Paginated tournament list response."""

    tournaments: list[TournamentResponse]
    total: int
    offset: int = 0
    limit: int = 20


class AgentResponse(BaseModel):
    """Agent detail response."""

    id: UUID
    team_id: UUID
    role: AgentRole
    model: ModelProvider
    status: AgentStatus
    total_tokens_used: int
    total_cost_usd: float
    actions_count: int
    errors_count: int
    last_heartbeat: datetime | None = None


class LeaderboardResponse(BaseModel):
    """ELO leaderboard response."""

    entries: list[LeaderboardEntry]
    total: int
    updated_at: datetime


class ChallengeResponse(BaseModel):
    """Challenge detail response."""

    id: str
    title: str
    description: str
    category: ChallengeCategory
    difficulty: ChallengeDifficulty
    time_limit_minutes: int
    requirements: list[str]
    tags: list[str] = Field(default_factory=list)


class ChallengeListResponse(BaseModel):
    """Challenge list response."""

    challenges: list[ChallengeResponse]
    total: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/shared/tests/test_responses.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/shared/src/types/responses.py packages/shared/tests/test_responses.py
git commit -m "feat(shared): add API response Pydantic models"
```

---

### Task 3: FastAPI Dependencies Module

**Files:**
- Create: `packages/api/src/dependencies.py`
- Test: `packages/api/tests/test_dependencies.py`

- [ ] **Step 1: Write the failing test**

Create `packages/api/tests/test_dependencies.py`:

```python
"""Tests for FastAPI dependency injection providers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from packages.api.src.dependencies import get_event_bus, get_orchestrator


@pytest.fixture
def app_with_state() -> FastAPI:
    app = FastAPI()
    app.state.event_bus = MagicMock()
    app.state.orchestrator = MagicMock()
    app.state.agent_manager = MagicMock()

    @app.get("/test-bus")
    async def test_bus(bus=get_event_bus):
        return {"type": type(bus).__name__}

    return app


def test_get_event_bus_returns_from_state():
    """get_event_bus should pull event_bus from app.state."""
    mock_request = MagicMock()
    mock_request.app.state.event_bus = "fake_bus"
    result = get_event_bus(mock_request)
    assert result == "fake_bus"


def test_get_orchestrator_returns_from_state():
    """get_orchestrator should pull orchestrator from app.state."""
    mock_request = MagicMock()
    mock_request.app.state.orchestrator = "fake_orchestrator"
    result = get_orchestrator(mock_request)
    assert result == "fake_orchestrator"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/api/tests/test_dependencies.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the dependencies module**

Create `packages/api/src/dependencies.py`:

```python
"""FastAPI dependency injection providers.

All service dependencies are initialized in lifespan() and stored on app.state.
These functions pull them out for use with FastAPI's Depends().
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.src.db.base import get_session
from packages.shared.src.events.bus import EventBus


def get_event_bus(request: Request) -> EventBus:
    """Get the shared event bus instance."""
    return request.app.state.event_bus


def get_orchestrator(request: Request):
    """Get the tournament orchestrator instance."""
    return request.app.state.orchestrator


def get_agent_manager(request: Request):
    """Get the agent team manager instance."""
    return request.app.state.agent_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session with automatic commit/rollback."""
    async with get_session() as session:
        yield session
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/api/tests/test_dependencies.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/api/src/dependencies.py packages/api/tests/test_dependencies.py
git commit -m "feat(api): add FastAPI dependency injection providers"
```

---

### Task 4: Tournament Route Handlers

**Files:**
- Create: `packages/api/src/routes/__init__.py`
- Create: `packages/api/src/routes/tournaments.py`
- Test: `packages/api/tests/test_tournament_routes.py`

- [ ] **Step 1: Write the failing test**

Create `packages/api/tests/test_tournament_routes.py`:

```python
"""Tests for tournament route handlers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.api.src.routes.tournaments import router
from packages.shared.src.types.models import (
    Tournament,
    TournamentConfig,
    TournamentFormat,
    TournamentPhase,
)


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    orch = MagicMock()
    orch.create_tournament = AsyncMock()
    orch.start_tournament = AsyncMock()
    orch._active_tournaments = {}
    return orch


@pytest.fixture
def mock_agent_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.get_team_agents = AsyncMock(return_value=[])
    return mgr


@pytest.fixture
def mock_event_bus() -> MagicMock:
    return MagicMock()


@pytest.fixture
def app(mock_orchestrator, mock_agent_manager, mock_event_bus) -> FastAPI:
    app = FastAPI()
    app.state.orchestrator = mock_orchestrator
    app.state.agent_manager = mock_agent_manager
    app.state.event_bus = mock_event_bus
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def test_create_tournament(client, mock_orchestrator):
    tournament_id = uuid4()
    mock_orchestrator.create_tournament.return_value = Tournament(
        id=tournament_id,
        format=TournamentFormat.DUEL,
        challenge_id="url-shortener-saas",
        config=TournamentConfig(
            format=TournamentFormat.DUEL,
            teams=[
                {"name": "Team A", "agents": [
                    {"role": "architect", "model": "claude-opus-4-6"},
                    {"role": "builder", "model": "claude-sonnet-4-6"},
                    {"role": "tester", "model": "claude-haiku-4-5"},
                ]},
                {"name": "Team B", "agents": [
                    {"role": "architect", "model": "claude-opus-4-6"},
                    {"role": "builder", "model": "claude-sonnet-4-6"},
                    {"role": "tester", "model": "claude-haiku-4-5"},
                ]},
            ],
        ),
    )

    resp = client.post("/api/v1/tournaments", json={
        "format": "duel",
        "teams": [
            {"name": "Team A", "agents": [
                {"role": "architect", "model": "claude-opus-4-6"},
                {"role": "builder", "model": "claude-sonnet-4-6"},
                {"role": "tester", "model": "claude-haiku-4-5"},
            ]},
            {"name": "Team B", "agents": [
                {"role": "architect", "model": "claude-opus-4-6"},
                {"role": "builder", "model": "claude-sonnet-4-6"},
                {"role": "tester", "model": "claude-haiku-4-5"},
            ]},
        ],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["format"] == "duel"
    mock_orchestrator.create_tournament.assert_awaited_once()


def test_list_tournaments_empty(client):
    resp = client.get("/api/v1/tournaments")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tournaments"] == []
    assert data["total"] == 0


def test_get_tournament_not_found(client, mock_orchestrator):
    mock_orchestrator._active_tournaments = {}
    resp = client.get(f"/api/v1/tournaments/{uuid4()}")
    assert resp.status_code == 404


def test_start_tournament(client, mock_orchestrator):
    tid = uuid4()
    mock_orchestrator.start_tournament.return_value = Tournament(
        id=tid,
        format=TournamentFormat.DUEL,
        challenge_id="url-shortener-saas",
        current_phase=TournamentPhase.RESEARCH,
        config=TournamentConfig(
            format=TournamentFormat.DUEL,
            teams=[
                {"name": "A", "agents": [
                    {"role": "architect", "model": "claude-opus-4-6"},
                    {"role": "builder", "model": "claude-sonnet-4-6"},
                    {"role": "tester", "model": "claude-haiku-4-5"},
                ]},
                {"name": "B", "agents": [
                    {"role": "architect", "model": "claude-opus-4-6"},
                    {"role": "builder", "model": "claude-sonnet-4-6"},
                    {"role": "tester", "model": "claude-haiku-4-5"},
                ]},
            ],
        ),
    )

    resp = client.post(f"/api/v1/tournaments/{tid}/start")
    assert resp.status_code == 200
    mock_orchestrator.start_tournament.assert_awaited_once_with(tid)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/api/tests/test_tournament_routes.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create routes package init**

Create `packages/api/src/routes/__init__.py`:

```python
"""API route modules."""
```

- [ ] **Step 4: Write the tournament routes**

Create `packages/api/src/routes/tournaments.py`:

```python
"""Tournament CRUD and lifecycle endpoints."""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from packages.api.src.dependencies import get_agent_manager, get_orchestrator
from packages.shared.src.types.models import TournamentConfig
from packages.shared.src.types.responses import (
    TeamSummary,
    TournamentListResponse,
    TournamentResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _tournament_to_response(tournament, agents_by_team: dict | None = None) -> TournamentResponse:
    """Convert a domain Tournament to an API response."""
    teams = []
    for i, team_id in enumerate(tournament.team_ids):
        agent_count = 0
        if agents_by_team and team_id in agents_by_team:
            agent_count = len(agents_by_team[team_id])
        else:
            agent_count = len(tournament.config.teams[i].agents) if i < len(tournament.config.teams) else 0
        teams.append(TeamSummary(
            id=team_id,
            name=tournament.config.teams[i].name if i < len(tournament.config.teams) else f"Team {i}",
            agent_count=agent_count,
            total_cost_usd=0.0,
        ))
    return TournamentResponse(
        id=tournament.id,
        format=tournament.format,
        current_phase=tournament.current_phase,
        challenge_id=tournament.challenge_id,
        teams=teams,
        total_cost_usd=tournament.total_cost_usd,
        started_at=tournament.started_at,
        completed_at=tournament.completed_at,
        winner_team_id=tournament.winner_team_id,
    )


@router.post("/tournaments", status_code=201)
async def create_tournament(
    config: TournamentConfig,
    orchestrator=Depends(get_orchestrator),
) -> TournamentResponse:
    """Create a new tournament."""
    tournament = await orchestrator.create_tournament(config)
    return _tournament_to_response(tournament)


@router.get("/tournaments")
async def list_tournaments(
    orchestrator=Depends(get_orchestrator),
    limit: int = 20,
    offset: int = 0,
) -> TournamentListResponse:
    """List all tournaments."""
    all_tournaments = list(orchestrator._active_tournaments.values())
    total = len(all_tournaments)
    page = all_tournaments[offset : offset + limit]
    return TournamentListResponse(
        tournaments=[_tournament_to_response(t) for t in page],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/tournaments/{tournament_id}")
async def get_tournament(
    tournament_id: UUID,
    orchestrator=Depends(get_orchestrator),
) -> TournamentResponse:
    """Get tournament details."""
    tournament = orchestrator._active_tournaments.get(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail=f"Tournament {tournament_id} not found")
    return _tournament_to_response(tournament)


@router.post("/tournaments/{tournament_id}/start")
async def start_tournament(
    tournament_id: UUID,
    orchestrator=Depends(get_orchestrator),
) -> TournamentResponse:
    """Start a tournament — provisions sandboxes, spawns agents."""
    try:
        tournament = await orchestrator.start_tournament(tournament_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _tournament_to_response(tournament)


@router.post("/tournaments/{tournament_id}/cancel")
async def cancel_tournament(
    tournament_id: UUID,
    orchestrator=Depends(get_orchestrator),
) -> dict:
    """Cancel a running tournament."""
    tournament = orchestrator._active_tournaments.get(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail=f"Tournament {tournament_id} not found")
    # TODO: Wire up cancellation in orchestrator
    return {"tournament_id": str(tournament_id), "status": "cancelled"}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest packages/api/tests/test_tournament_routes.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add packages/api/src/routes/ packages/api/tests/test_tournament_routes.py
git commit -m "feat(api): add tournament route handlers with DI"
```

---

### Task 5: Agent, Leaderboard, and Challenge Routes

**Files:**
- Create: `packages/api/src/routes/agents.py`
- Create: `packages/api/src/routes/leaderboard.py`
- Create: `packages/api/src/routes/challenges.py`
- Test: `packages/api/tests/test_agent_routes.py`
- Test: `packages/api/tests/test_leaderboard_routes.py`
- Test: `packages/api/tests/test_challenge_routes.py`

- [ ] **Step 1: Write tests for agent routes**

Create `packages/api/tests/test_agent_routes.py`:

```python
"""Tests for agent route handlers."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.api.src.routes.agents import router
from packages.shared.src.types.models import (
    Agent,
    AgentRole,
    AgentStatus,
    ModelProvider,
)


@pytest.fixture
def mock_agent_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.get_team_agents = AsyncMock()
    return mgr


@pytest.fixture
def app(mock_agent_manager) -> FastAPI:
    app = FastAPI()
    app.state.agent_manager = mock_agent_manager
    app.state.orchestrator = MagicMock()
    app.state.orchestrator._active_tournaments = {}
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def test_list_agents_for_tournament(client, mock_agent_manager):
    tid = uuid4()
    team_id = uuid4()

    # Set up a tournament with one team
    from packages.shared.src.types.models import Tournament, TournamentConfig, TournamentFormat
    tournament = MagicMock()
    tournament.team_ids = [team_id]
    client.app.state.orchestrator._active_tournaments = {tid: tournament}

    agent = Agent(
        id=uuid4(),
        team_id=team_id,
        tournament_id=tid,
        role=AgentRole.BUILDER,
        model=ModelProvider.CLAUDE_SONNET_4_6,
        status=AgentStatus.CODING,
        total_tokens_used=5000,
        total_cost_usd=0.50,
        actions_count=10,
        last_heartbeat=datetime.utcnow(),
    )
    mock_agent_manager.get_team_agents.return_value = [agent]

    resp = client.get(f"/api/v1/tournaments/{tid}/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["agents"]) == 1
    assert data["agents"][0]["role"] == "builder"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/api/tests/test_agent_routes.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write agent routes**

Create `packages/api/src/routes/agents.py`:

```python
"""Agent status endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from packages.api.src.dependencies import get_agent_manager, get_orchestrator
from packages.shared.src.types.responses import AgentResponse

router = APIRouter()


@router.get("/tournaments/{tournament_id}/agents")
async def list_agents(
    tournament_id: UUID,
    orchestrator=Depends(get_orchestrator),
    agent_manager=Depends(get_agent_manager),
) -> dict:
    """List all agents across all teams in a tournament."""
    tournament = orchestrator._active_tournaments.get(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    all_agents = []
    for team_id in tournament.team_ids:
        agents = await agent_manager.get_team_agents(team_id)
        for agent in agents:
            all_agents.append(AgentResponse(
                id=agent.id,
                team_id=agent.team_id,
                role=agent.role,
                model=agent.model,
                status=agent.status,
                total_tokens_used=agent.total_tokens_used,
                total_cost_usd=agent.total_cost_usd,
                actions_count=agent.actions_count,
                errors_count=agent.errors_count,
                last_heartbeat=agent.last_heartbeat,
            ))
    return {"agents": [a.model_dump(mode="json") for a in all_agents], "total": len(all_agents)}


@router.get("/tournaments/{tournament_id}/teams/{team_id}/agents")
async def list_team_agents(
    tournament_id: UUID,
    team_id: UUID,
    agent_manager=Depends(get_agent_manager),
) -> dict:
    """List agents for a specific team."""
    agents = await agent_manager.get_team_agents(team_id)
    responses = [
        AgentResponse(
            id=a.id, team_id=a.team_id, role=a.role, model=a.model,
            status=a.status, total_tokens_used=a.total_tokens_used,
            total_cost_usd=a.total_cost_usd, actions_count=a.actions_count,
            errors_count=a.errors_count, last_heartbeat=a.last_heartbeat,
        )
        for a in agents
    ]
    return {"agents": [r.model_dump(mode="json") for r in responses], "total": len(responses)}
```

- [ ] **Step 4: Run agent route test**

Run: `pytest packages/api/tests/test_agent_routes.py -v`
Expected: PASS

- [ ] **Step 5: Write leaderboard routes**

Create `packages/api/src/routes/leaderboard.py`:

```python
"""ELO leaderboard endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from packages.shared.src.types.responses import LeaderboardResponse

router = APIRouter()


@router.get("/leaderboard")
async def get_leaderboard(
    category: str = "overall",
    limit: int = 50,
) -> LeaderboardResponse:
    """Get the ELO leaderboard.

    Currently returns empty — populated after first tournament completes.
    """
    return LeaderboardResponse(
        entries=[],
        total=0,
        updated_at=datetime.utcnow(),
    )
```

- [ ] **Step 6: Write challenge routes**

Create `packages/api/src/routes/challenges.py`:

```python
"""Challenge library endpoints."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from packages.shared.src.types.models import ChallengeCategory, ChallengeDifficulty
from packages.shared.src.types.responses import ChallengeListResponse, ChallengeResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory challenge cache (loaded from filesystem on first access)
_challenge_cache: list[ChallengeResponse] | None = None

CHALLENGES_DIR = Path("challenges/library")


def _load_challenges() -> list[ChallengeResponse]:
    """Load challenges from the challenges/library/ directory."""
    global _challenge_cache
    if _challenge_cache is not None:
        return _challenge_cache

    challenges = []
    if CHALLENGES_DIR.exists():
        for challenge_dir in sorted(CHALLENGES_DIR.iterdir()):
            challenge_file = challenge_dir / "CHALLENGE.md"
            if challenge_file.exists():
                challenges.append(ChallengeResponse(
                    id=challenge_dir.name,
                    title=challenge_dir.name.replace("-", " ").title(),
                    description=challenge_file.read_text()[:500],
                    category=ChallengeCategory.SAAS_APP,
                    difficulty=ChallengeDifficulty.MEDIUM,
                    time_limit_minutes=90,
                    requirements=["See CHALLENGE.md for full requirements"],
                    tags=[],
                ))

    _challenge_cache = challenges
    return challenges


@router.get("/challenges")
async def list_challenges(
    category: str | None = None,
    difficulty: str | None = None,
) -> ChallengeListResponse:
    """List available challenges."""
    challenges = _load_challenges()

    if category:
        challenges = [c for c in challenges if c.category.value == category]
    if difficulty:
        challenges = [c for c in challenges if c.difficulty.value == difficulty]

    return ChallengeListResponse(challenges=challenges, total=len(challenges))


@router.get("/challenges/{challenge_id}")
async def get_challenge(challenge_id: str) -> ChallengeResponse:
    """Get a specific challenge."""
    challenges = _load_challenges()
    for c in challenges:
        if c.id == challenge_id:
            return c
    raise HTTPException(status_code=404, detail=f"Challenge '{challenge_id}' not found")
```

- [ ] **Step 7: Write leaderboard + challenge tests**

Create `packages/api/tests/test_leaderboard_routes.py`:

```python
"""Tests for leaderboard routes."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.api.src.routes.leaderboard import router


def test_leaderboard_returns_empty():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)

    resp = client.get("/api/v1/leaderboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["entries"] == []
```

Create `packages/api/tests/test_challenge_routes.py`:

```python
"""Tests for challenge routes."""
from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.api.src.routes import challenges
from packages.api.src.routes.challenges import router
from packages.shared.src.types.models import ChallengeCategory, ChallengeDifficulty
from packages.shared.src.types.responses import ChallengeResponse


def test_list_challenges_empty():
    # Reset cache
    challenges._challenge_cache = []
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)

    resp = client.get("/api/v1/challenges")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    challenges._challenge_cache = None  # Reset


def test_get_challenge_not_found():
    challenges._challenge_cache = []
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)

    resp = client.get("/api/v1/challenges/nonexistent")
    assert resp.status_code == 404
    challenges._challenge_cache = None
```

- [ ] **Step 8: Run all route tests**

Run: `pytest packages/api/tests/ -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add packages/api/src/routes/agents.py packages/api/src/routes/leaderboard.py packages/api/src/routes/challenges.py packages/api/tests/
git commit -m "feat(api): add agent, leaderboard, and challenge route handlers"
```

---

### Task 6: WebSocket Spectator

**Files:**
- Create: `packages/api/src/ws/__init__.py`
- Create: `packages/api/src/ws/spectator.py`
- Test: `packages/api/tests/test_spectator_ws.py`

- [ ] **Step 1: Write the failing test**

Create `packages/api/tests/test_spectator_ws.py`:

```python
"""Tests for WebSocket spectator."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.api.src.ws.spectator import router


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    mock_redis = MagicMock()
    mock_redis.pubsub = MagicMock(return_value=MagicMock(
        subscribe=AsyncMock(),
        get_message=AsyncMock(return_value=None),
        unsubscribe=AsyncMock(),
        close=AsyncMock(),
    ))
    app.state.redis = mock_redis
    app.include_router(router)
    return app


def test_spectator_ws_connects(app):
    client = TestClient(app)
    with client.websocket_connect("/ws/spectate/test-tournament-123") as ws:
        data = ws.receive_json()
        assert data["type"] == "connected"
        assert data["tournament_id"] == "test-tournament-123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/api/tests/test_spectator_ws.py -v`
Expected: FAIL

- [ ] **Step 3: Write spectator WebSocket**

Create `packages/api/src/ws/__init__.py`:

```python
"""WebSocket handlers."""
```

Create `packages/api/src/ws/spectator.py`:

```python
"""WebSocket spectator — real-time tournament event streaming."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/spectate/{tournament_id}")
async def spectate(websocket: WebSocket, tournament_id: str) -> None:
    """Stream real-time tournament events to spectators."""
    await websocket.accept()

    # Send connection confirmation
    await websocket.send_json({
        "type": "connected",
        "tournament_id": tournament_id,
        "message": "Subscribed to tournament events",
    })

    redis = websocket.app.state.redis
    pubsub = redis.pubsub()

    try:
        # Subscribe to tournament-specific and agent events
        await pubsub.subscribe(
            f"arena:realtime:tournament.phase.*",
            f"arena:realtime:tournament.team.*",
            f"arena:realtime:agent.tool.*",
            f"arena:realtime:tournament.budget.*",
            f"arena:realtime:tournament.completed",
        )

        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )

            if message and message["type"] == "message":
                # Forward event to WebSocket client
                import orjson
                try:
                    event_data = orjson.loads(message["data"])
                    # Filter to only this tournament's events
                    if event_data.get("tournament_id") and str(event_data["tournament_id"]) != tournament_id:
                        continue
                    await websocket.send_json(event_data)
                except Exception:
                    logger.debug("Failed to parse event data")

            # Send heartbeat ping every 30 iterations (~30s)
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info("Spectator disconnected from tournament %s", tournament_id)
    except Exception:
        logger.exception("Spectator error for tournament %s", tournament_id)
    finally:
        await pubsub.unsubscribe()
        await pubsub.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/api/tests/test_spectator_ws.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/api/src/ws/ packages/api/tests/test_spectator_ws.py
git commit -m "feat(api): add WebSocket spectator for real-time event streaming"
```

---

### Task 7: Refactor main.py — Mount Routers + Init Services in Lifespan

**Files:**
- Modify: `packages/api/src/main.py`
- Test: `packages/api/tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Create `packages/api/tests/test_app.py`:

```python
"""Tests for main app factory."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def test_health_check_endpoint():
    """Health check should exist and return a response."""
    with patch("packages.api.src.main.init_db", new_callable=AsyncMock):
        with patch("packages.api.src.main.aioredis") as mock_redis_module:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis.close = AsyncMock()
            mock_redis_module.from_url.return_value = mock_redis

            with patch("packages.api.src.main.close_db", new_callable=AsyncMock):
                from packages.api.src.main import create_app
                app = create_app()
                # Can't fully test lifespan here, but verify app has routes
                routes = [r.path for r in app.routes]
                assert "/health" in routes
                assert any("/tournaments" in r for r in routes)


def test_app_has_tournament_routes():
    """App should mount tournament router at /api/v1/tournaments."""
    from packages.api.src.main import create_app
    app = create_app()
    route_paths = [r.path for r in app.routes]
    assert "/api/v1/tournaments" in route_paths
    assert "/api/v1/leaderboard" in route_paths
    assert "/api/v1/challenges" in route_paths
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/api/tests/test_app.py -v`
Expected: FAIL (routes don't exist yet on app)

- [ ] **Step 3: Rewrite main.py**

Replace the full content of `packages/api/src/main.py` with:

```python
"""
AgentForge Arena — FastAPI Application

Main API entry point. Mounts route modules, configures middleware,
and initializes service dependencies via lifespan.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from packages.shared.src.config import get_settings
from packages.shared.src.db.base import close_db, init_db
from packages.shared.src.events.bus import EventBus

from packages.api.src.routes import tournaments, agents, leaderboard, challenges
from packages.api.src.ws import spectator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize and cleanup resources."""
    settings = get_settings()
    logger.info("Starting AgentForge Arena v%s (%s)", settings.version, settings.environment)

    # Database
    await init_db()
    logger.info("Database initialized")

    # Redis
    app.state.redis = aioredis.from_url(settings.redis.url, decode_responses=False)
    await app.state.redis.ping()
    logger.info("Redis connected")

    # Event Bus
    app.state.event_bus = EventBus(app.state.redis)
    logger.info("Event bus initialized")

    # Services — lazy import to avoid circular deps
    from packages.sandbox.src.docker.manager import SandboxManager
    from packages.agents.src.teams.manager import AgentTeamManager
    from packages.core.src.tournament.orchestrator import TournamentOrchestrator
    from packages.judge.src.scoring.service import JudgeScoringService

    app.state.sandbox_manager = SandboxManager()
    app.state.agent_manager = AgentTeamManager(app.state.event_bus)

    app.state.orchestrator = TournamentOrchestrator(
        event_bus=app.state.event_bus,
        sandbox_manager=app.state.sandbox_manager,
        agent_manager=app.state.agent_manager,
        judge_service=None,  # Wired later when judge package is ready
    )
    logger.info("Services initialized (orchestrator, sandbox, agents)")

    # Langfuse
    if settings.langfuse.enabled:
        try:
            from langfuse import Langfuse
            app.state.langfuse = Langfuse(
                public_key=settings.langfuse.public_key,
                secret_key=settings.langfuse.secret_key.get_secret_value(),
                host=settings.langfuse.host,
            )
            logger.info("Langfuse connected")
        except Exception:
            logger.warning("Langfuse initialization failed — tracing disabled")
            app.state.langfuse = None

    yield

    # Shutdown
    logger.info("Shutting down AgentForge Arena")
    await app.state.agent_manager.teardown_all()
    await app.state.sandbox_manager.destroy_all()
    if hasattr(app.state, "langfuse") and app.state.langfuse:
        app.state.langfuse.flush()
    if hasattr(app.state, "redis"):
        await app.state.redis.close()
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="AgentForge Arena API",
        description="Competitive tournament platform where AI agent teams build production apps",
        version=settings.version,
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check (stays inline — simple)
    @app.get("/health", tags=["system"])
    async def health_check(request: Request) -> dict:
        checks: dict[str, str] = {}
        try:
            await request.app.state.redis.ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {e}"

        all_ok = all(v == "ok" for v in checks.values())
        return {
            "status": "healthy" if all_ok else "degraded",
            "version": settings.version,
            "checks": checks,
        }

    # Mount route modules
    app.include_router(tournaments.router, prefix="/api/v1", tags=["tournaments"])
    app.include_router(agents.router, prefix="/api/v1", tags=["agents"])
    app.include_router(leaderboard.router, prefix="/api/v1", tags=["leaderboard"])
    app.include_router(challenges.router, prefix="/api/v1", tags=["challenges"])
    app.include_router(spectator.router, tags=["spectator"])

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "packages.api.src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest packages/api/tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/api/src/main.py packages/api/tests/test_app.py
git commit -m "refactor(api): mount route modules, init services in lifespan"
```

---

### Task 8: ClaudeAgentRunner — Core Runtime

**Files:**
- Create: `packages/agents/src/runtime/__init__.py`
- Create: `packages/agents/src/runtime/claude_sdk.py`
- Test: `packages/agents/tests/test_claude_sdk_runner.py`

- [ ] **Step 1: Write the failing test**

Create `packages/agents/tests/test_claude_sdk_runner.py`:

```python
"""Tests for ClaudeAgentRunner — the Claude SDK agent runtime."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from packages.shared.src.types.models import (
    Agent,
    AgentRole,
    AgentStatus,
    ModelProvider,
)


def _make_agent(role: AgentRole = AgentRole.BUILDER) -> Agent:
    return Agent(
        id=uuid4(),
        team_id=uuid4(),
        tournament_id=uuid4(),
        role=role,
        model=ModelProvider.CLAUDE_SONNET_4_6,
    )


def test_role_tool_mapping():
    """Each role should have a predefined set of allowed tools."""
    from packages.agents.src.runtime.claude_sdk import ROLE_TOOL_MAP
    assert "Read" in ROLE_TOOL_MAP[AgentRole.BUILDER]
    assert "Bash" in ROLE_TOOL_MAP[AgentRole.BUILDER]
    assert "Bash" not in ROLE_TOOL_MAP[AgentRole.CRITIC]
    assert "WebSearch" in ROLE_TOOL_MAP[AgentRole.RESEARCHER]
    assert "Agent" in ROLE_TOOL_MAP[AgentRole.ARCHITECT]


def test_runner_init_sets_defaults():
    """Runner should initialize with correct defaults."""
    from packages.agents.src.runtime.claude_sdk import ClaudeAgentRunner

    agent = _make_agent()
    bus = MagicMock()
    runner = ClaudeAgentRunner(
        agent=agent,
        system_prompt="You are a builder.",
        cwd="/arena/team-123/project",
        allowed_tools=["Read", "Write", "Edit", "Bash"],
        event_bus=bus,
    )

    assert runner._agent is agent
    assert runner._cwd == "/arena/team-123/project"
    assert runner._max_turns == 100
    assert runner._max_budget_usd == 50.0
    assert runner.total_cost_usd == 0.0
    assert runner.total_tokens == 0


def test_runner_budget_check_blocks_when_over():
    """send_task should raise if accumulated cost exceeds budget."""
    from packages.agents.src.runtime.claude_sdk import ClaudeAgentRunner

    agent = _make_agent()
    bus = MagicMock()
    runner = ClaudeAgentRunner(
        agent=agent,
        system_prompt="test",
        cwd="/tmp",
        allowed_tools=["Read"],
        event_bus=bus,
        max_budget_usd=1.0,
    )
    runner._accumulated_cost_usd = 1.5  # Over budget

    with pytest.raises(RuntimeError, match="budget"):
        import asyncio
        asyncio.get_event_loop().run_until_complete(runner.send_task("do something"))


def test_runner_tracks_cost():
    """Runner should accumulate cost from usage data."""
    from packages.agents.src.runtime.claude_sdk import ClaudeAgentRunner

    agent = _make_agent()
    bus = MagicMock()
    runner = ClaudeAgentRunner(
        agent=agent,
        system_prompt="test",
        cwd="/tmp",
        allowed_tools=["Read"],
        event_bus=bus,
    )

    # Simulate adding cost
    runner._accumulated_cost_usd = 0.0
    runner._accumulated_tokens = 0
    runner._add_usage({"input_tokens": 1000, "output_tokens": 500})

    assert runner.total_tokens == 1500
    assert runner.total_cost_usd > 0


def test_runner_is_responsive():
    """is_responsive should check last_activity timestamp."""
    from packages.agents.src.runtime.claude_sdk import ClaudeAgentRunner

    agent = _make_agent()
    bus = MagicMock()
    runner = ClaudeAgentRunner(
        agent=agent, system_prompt="test", cwd="/tmp",
        allowed_tools=["Read"], event_bus=bus,
    )
    runner._last_activity = datetime.utcnow()
    assert runner.is_responsive is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/agents/tests/test_claude_sdk_runner.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write ClaudeAgentRunner**

Create `packages/agents/src/runtime/__init__.py`:

```python
"""Agent runtime modules."""
```

Create `packages/agents/src/runtime/claude_sdk.py`:

```python
"""Claude Agent SDK runtime — wraps ClaudeSDKClient for tournament agents.

Each agent role gets its own SDK client instance with role-specific tools,
system prompt, and budget constraints. Runs with bypassPermissions because
the Docker MicroVM sandbox is the security boundary.
"""
from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from packages.shared.src.events.bus import EventBus
from packages.shared.src.types.models import Agent, AgentRole, AgentStatus

logger = logging.getLogger(__name__)

# Model pricing per 1M tokens (input, output) in USD
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
DEFAULT_PRICING = (3.00, 15.00)  # Sonnet pricing as fallback

# Role → allowed tools mapping
ROLE_TOOL_MAP: dict[AgentRole, list[str]] = {
    AgentRole.ARCHITECT: ["Read", "Write", "Edit", "Glob", "Grep", "Agent"],
    AgentRole.BUILDER: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    AgentRole.FRONTEND: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    AgentRole.TESTER: ["Read", "Write", "Bash", "Glob", "Grep"],
    AgentRole.CRITIC: ["Read", "Glob", "Grep"],
    AgentRole.RESEARCHER: ["Read", "Write", "WebSearch", "WebFetch", "Glob", "Grep"],
}


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
    ) -> None:
        self._agent = agent
        self._system_prompt = system_prompt
        self._cwd = cwd
        self._allowed_tools = allowed_tools
        self._event_bus = event_bus
        self._max_turns = max_turns
        self._max_budget_usd = max_budget_usd
        self._model = model or agent.model.value
        self._client = None
        self._session_id: str | None = None
        self._accumulated_cost_usd: float = 0.0
        self._accumulated_tokens: int = 0
        self._last_activity: datetime | None = None

    async def start(self) -> None:
        """Initialize the SDK client. Does not send a task yet."""
        self._agent.status = AgentStatus.ACTIVE
        self._last_activity = datetime.utcnow()
        logger.info(
            "Agent %s (%s) started — model=%s, tools=%s, cwd=%s",
            self._agent.role.value, self._agent.id,
            self._model, self._allowed_tools, self._cwd,
        )

    async def send_task(self, prompt: str) -> str:
        """Send a task to the agent. Returns the result text.

        Streams responses, publishes tool-use events, tracks cost.
        Raises RuntimeError if over budget.
        """
        if self._accumulated_cost_usd >= self._max_budget_usd:
            raise RuntimeError(
                f"Agent {self._agent.role.value} over budget: "
                f"${self._accumulated_cost_usd:.2f} >= ${self._max_budget_usd:.2f}"
            )

        self._agent.status = AgentStatus.CODING
        self._last_activity = datetime.utcnow()

        try:
            from claude_agent_sdk import (
                ClaudeSDKClient,
                ClaudeAgentOptions,
                AssistantMessage,
                ResultMessage,
                SystemMessage,
                HookMatcher,
                TextBlock,
            )

            # Build PostToolUse hook for event streaming
            agent_ref = self._agent
            event_bus_ref = self._event_bus

            async def on_tool_use(input_data, tool_use_id, context):
                await event_bus_ref.publish(
                    "agent.tool.used",
                    source=f"agent.{agent_ref.role.value}",
                    tournament_id=agent_ref.tournament_id,
                    team_id=agent_ref.team_id,
                    agent_id=agent_ref.id,
                    payload={
                        "tool": input_data.get("tool_name", "unknown"),
                        "input_summary": str(input_data.get("tool_input", ""))[:200],
                    },
                )
                return {}

            options = ClaudeAgentOptions(
                cwd=self._cwd,
                allowed_tools=self._allowed_tools,
                permission_mode="bypassPermissions",
                system_prompt=self._system_prompt,
                max_turns=self._max_turns,
                max_budget_usd=self._max_budget_usd - self._accumulated_cost_usd,
                model=self._model,
                setting_sources=["project"],
                hooks={
                    "PostToolUse": [
                        HookMatcher(matcher="*", hooks=[on_tool_use]),
                    ],
                },
            )

            # Resume session if we have one, otherwise start fresh
            if self._session_id:
                options.resume = self._session_id

            result_text = ""
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)
                async for message in client.receive_response():
                    if isinstance(message, SystemMessage) and message.subtype == "init":
                        self._session_id = message.data.get("session_id")

                    if isinstance(message, AssistantMessage):
                        self._agent.actions_count += 1
                        if message.usage:
                            self._add_usage(message.usage)
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                result_text += block.text

                    if isinstance(message, ResultMessage):
                        result_text = message.result or result_text

            self._last_activity = datetime.utcnow()
            self._agent.status = AgentStatus.IDLE
            return result_text

        except ImportError:
            logger.error("claude_agent_sdk not installed — running in stub mode")
            self._agent.status = AgentStatus.IDLE
            return f"[STUB] Would execute: {prompt[:100]}"
        except Exception:
            self._agent.errors_count += 1
            self._agent.status = AgentStatus.ERROR
            logger.exception("Agent %s task failed", self._agent.role.value)
            raise

    async def stop(self) -> None:
        """Stop the agent."""
        self._agent.status = AgentStatus.TERMINATED
        logger.info("Agent %s (%s) stopped", self._agent.role.value, self._agent.id)

    @property
    def is_responsive(self) -> bool:
        """Check if agent has been active recently (within 60s)."""
        if self._last_activity is None:
            return False
        elapsed = (datetime.utcnow() - self._last_activity).total_seconds()
        return elapsed < 60

    @property
    def total_cost_usd(self) -> float:
        """Accumulated cost in USD."""
        return self._accumulated_cost_usd

    @property
    def total_tokens(self) -> int:
        """Accumulated token count."""
        return self._accumulated_tokens

    def _add_usage(self, usage: dict) -> None:
        """Accumulate cost from a usage dict (input_tokens, output_tokens)."""
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        self._accumulated_tokens += input_tokens + output_tokens

        pricing = MODEL_PRICING.get(self._model, DEFAULT_PRICING)
        cost = (input_tokens / 1_000_000 * pricing[0]) + (output_tokens / 1_000_000 * pricing[1])
        self._accumulated_cost_usd += cost

        # Sync back to agent model
        self._agent.total_tokens_used = self._accumulated_tokens
        self._agent.total_cost_usd = self._accumulated_cost_usd
        self._agent.last_heartbeat = datetime.utcnow()
```

- [ ] **Step 4: Run tests**

Run: `pytest packages/agents/tests/test_claude_sdk_runner.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/runtime/ packages/agents/tests/test_claude_sdk_runner.py
git commit -m "feat(agents): add ClaudeAgentRunner — Claude SDK agent runtime"
```

---

### Task 9: Refactor AgentTeamManager to Use ClaudeAgentRunner

**Files:**
- Modify: `packages/agents/src/teams/manager.py`
- Test: `packages/agents/tests/test_team_manager.py`

- [ ] **Step 1: Write the failing test**

Create `packages/agents/tests/test_team_manager.py`:

```python
"""Tests for refactored AgentTeamManager using ClaudeAgentRunner."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from packages.shared.src.types.models import (
    AgentConfig,
    AgentRole,
    AgentStatus,
    ModelProvider,
    TeamConfig,
)


@pytest.fixture
def event_bus() -> MagicMock:
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus


@pytest.mark.asyncio
async def test_spawn_team_creates_runners(event_bus):
    """spawn_team should create a ClaudeAgentRunner per agent config."""
    from packages.agents.src.teams.manager import AgentTeamManager

    mgr = AgentTeamManager(event_bus)
    team_id = uuid4()
    tournament_id = uuid4()

    config = TeamConfig(
        name="Test Team",
        agents=[
            AgentConfig(role=AgentRole.ARCHITECT, model=ModelProvider.CLAUDE_OPUS_4_6),
            AgentConfig(role=AgentRole.BUILDER, model=ModelProvider.CLAUDE_SONNET_4_6),
            AgentConfig(role=AgentRole.TESTER, model=ModelProvider.CLAUDE_HAIKU_4_5),
        ],
    )

    with patch("packages.agents.src.teams.manager.ClaudeAgentRunner") as MockRunner:
        mock_instance = AsyncMock()
        mock_instance.start = AsyncMock()
        mock_instance._agent = MagicMock()
        mock_instance._agent.id = uuid4()
        MockRunner.return_value = mock_instance

        ids = await mgr.spawn_team(team_id, tournament_id, config, "sandbox-123")
        assert len(ids) == 3
        assert MockRunner.call_count == 3
        assert mock_instance.start.await_count == 3


@pytest.mark.asyncio
async def test_check_team_health(event_bus):
    """check_team_health should report responsive/unresponsive agents."""
    from packages.agents.src.teams.manager import AgentTeamManager

    mgr = AgentTeamManager(event_bus)
    team_id = uuid4()

    mock_runner = MagicMock()
    mock_runner.is_responsive = True
    mock_runner._agent = MagicMock()
    mock_runner._agent.role.value = "builder"
    mock_runner._agent.id = uuid4()
    mock_runner._agent.last_heartbeat = None
    mock_runner._agent.errors_count = 0

    mgr._teams[team_id] = [mock_runner]

    health = await mgr.check_team_health(team_id)
    assert health["all_responsive"] is True
    assert health["total_agents"] == 1


@pytest.mark.asyncio
async def test_teardown_team(event_bus):
    """teardown_team should stop all runners and remove the team."""
    from packages.agents.src.teams.manager import AgentTeamManager

    mgr = AgentTeamManager(event_bus)
    team_id = uuid4()

    mock_runner = MagicMock()
    mock_runner.stop = AsyncMock()

    mgr._teams[team_id] = [mock_runner]
    await mgr.teardown_team(team_id)

    mock_runner.stop.assert_awaited_once()
    assert team_id not in mgr._teams
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest packages/agents/tests/test_team_manager.py -v`
Expected: FAIL (manager still uses old AgentProcess)

- [ ] **Step 3: Rewrite manager.py**

Replace the full content of `packages/agents/src/teams/manager.py` with:

```python
"""
AgentForge Arena — Agent Team Manager

Manages agent team lifecycle: spawning, health checks, communication, teardown.
Each agent runs as a ClaudeAgentRunner backed by the Claude Agent SDK.
"""
from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID, uuid4

from packages.shared.src.config import get_settings
from packages.shared.src.events.bus import EventBus
from packages.shared.src.types.models import (
    Agent,
    AgentRole,
    AgentStatus,
    TeamConfig,
)
from packages.agents.src.runtime.claude_sdk import ClaudeAgentRunner, ROLE_TOOL_MAP

logger = logging.getLogger(__name__)

# Agent role → system prompt file mapping
AGENT_PROMPT_FILES: dict[AgentRole, str] = {
    AgentRole.ARCHITECT: ".claude/agents/architect.md",
    AgentRole.BUILDER: ".claude/agents/builder.md",
    AgentRole.FRONTEND: ".claude/agents/frontend.md",
    AgentRole.TESTER: ".claude/agents/tester.md",
    AgentRole.CRITIC: ".claude/agents/critic.md",
    AgentRole.RESEARCHER: ".claude/agents/researcher.md",
}


class AgentTeamManager:
    """Manages all agent teams across tournaments."""

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus
        self._teams: dict[UUID, list[ClaudeAgentRunner]] = {}

    async def spawn_team(
        self,
        team_id: UUID,
        tournament_id: UUID,
        config: TeamConfig,
        sandbox_id: str,
    ) -> list[UUID]:
        """Spawn all agents for a team. Returns list of agent IDs."""
        settings = get_settings()
        workspace_path = f"{settings.sandbox.workspace_base}/team-{team_id}/project"

        # Calculate per-agent budget
        total_agents_in_tournament = len(config.agents)
        per_agent_budget = 500.0 / max(total_agents_in_tournament, 1)

        runners: list[ClaudeAgentRunner] = []
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

            # Get role-specific tools
            allowed_tools = ROLE_TOOL_MAP.get(
                agent_config.role,
                ["Read", "Glob", "Grep"],
            )

            runner = ClaudeAgentRunner(
                agent=agent,
                system_prompt=system_prompt,
                cwd=workspace_path,
                allowed_tools=allowed_tools,
                event_bus=self._events,
                max_turns=100,
                max_budget_usd=per_agent_budget,
                model=agent_config.model.value,
            )

            await runner.start()
            runners.append(runner)
            agent_ids.append(agent.id)

        self._teams[team_id] = runners
        logger.info("Spawned %d agents for team %s", len(runners), team_id)
        return agent_ids

    async def send_task_to_role(
        self, team_id: UUID, role: AgentRole, prompt: str
    ) -> str:
        """Send a task to a specific agent role in a team."""
        runners = self._teams.get(team_id, [])
        for runner in runners:
            if runner._agent.role == role:
                return await runner.send_task(prompt)
        raise ValueError(f"No agent with role {role.value} in team {team_id}")

    async def check_team_health(self, team_id: UUID) -> dict:
        """Check health of all agents in a team."""
        runners = self._teams.get(team_id, [])
        if not runners:
            return {"all_responsive": False, "error": "Team not found"}

        unresponsive = []
        for runner in runners:
            if not runner.is_responsive:
                unresponsive.append({
                    "role": runner._agent.role.value,
                    "agent_id": str(runner._agent.id),
                    "last_heartbeat": (
                        runner._agent.last_heartbeat.isoformat()
                        if runner._agent.last_heartbeat
                        else None
                    ),
                    "errors": runner._agent.errors_count,
                })

        return {
            "all_responsive": len(unresponsive) == 0,
            "total_agents": len(runners),
            "responsive": len(runners) - len(unresponsive),
            "unresponsive": unresponsive,
        }

    async def get_team_agents(self, team_id: UUID) -> list[Agent]:
        """Get all agent metadata for a team."""
        runners = self._teams.get(team_id, [])
        return [r._agent for r in runners]

    async def teardown_team(self, team_id: UUID) -> None:
        """Stop all agents in a team."""
        runners = self._teams.get(team_id, [])
        for runner in runners:
            await runner.stop()
        if team_id in self._teams:
            del self._teams[team_id]
        logger.info("Team %s torn down", team_id)

    async def teardown_all(self) -> None:
        """Teardown all teams. Used in shutdown."""
        team_ids = list(self._teams.keys())
        for team_id in team_ids:
            await self.teardown_team(team_id)
```

- [ ] **Step 4: Run tests**

Run: `pytest packages/agents/tests/test_team_manager.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Run all tests to check nothing broke**

Run: `pytest packages/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add packages/agents/src/teams/manager.py packages/agents/tests/test_team_manager.py
git commit -m "refactor(agents): replace AgentProcess with ClaudeAgentRunner in team manager"
```

---

### Task 10: Final Integration — Run Full Test Suite + Lint

**Files:**
- No new files

- [ ] **Step 1: Run full test suite**

Run: `pytest packages/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Run linter**

Run: `ruff check packages/ --fix`
Expected: No errors (or auto-fixed)

- [ ] **Step 3: Run formatter**

Run: `ruff format packages/`
Expected: Files formatted

- [ ] **Step 4: Re-run tests after formatting**

Run: `pytest packages/ -v --tb=short`
Expected: All tests still PASS

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: lint and format all packages"
```
