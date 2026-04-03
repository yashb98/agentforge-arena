# AgentForge Arena — Full Architecture Overview

> Competitive tournament platform — AI agent teams build production apps in hackathon-style challenges.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        packages/web (Next.js 15)                        │
│  Landing │ Arena Spectator │ Leaderboard │ Replay │ Challenge Library   │
│  Socket.IO client ← real-time events                                    │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ HTTP + WebSocket
┌────────────────────────────────▼────────────────────────────────────────┐
│                      packages/api (FastAPI Gateway)                     │
│  /api/v1/tournaments │ /api/v1/leaderboard │ /api/v1/challenges        │
│  /api/v1/agents      │ /health             │ WebSocket: /ws/spectator   │
└──┬─────────┬─────────┬─────────────┬───────────────┬───────────────────┘
   │         │         │             │               │
   ▼         ▼         ▼             ▼               ▼
 core    sandbox    agents        judge          spectator
```

---

## 10 Packages & What They Do

| Package | Role | Key File |
|---------|------|----------|
| **shared** | Foundation — types, DB, Redis, events, config, LLM client. ZERO imports from other packages | `src/types/models.py`, `src/events/bus.py`, `src/llm/client.py`, `src/config.py` |
| **core** | Tournament orchestrator — lifecycle state machine, phase transitions, timing, ELO | `src/tournament/orchestrator.py`, `src/elo/calculator.py` |
| **sandbox** | Docker MicroVM management — create/destroy isolated environments per team | `src/docker/manager.py` |
| **agents** | Agent team lifecycle — spawn, communicate via Redis mailbox, health check, teardown | `src/teams/manager.py`, `src/communication/mailbox.py` |
| **judge** | Multi-dimension scoring — automated (pytest, ruff, coverage) + LLM (UX, architecture, innovation) | `src/scoring/service.py` |
| **spectator** | Real-time streaming — Redis Pub/Sub -> Socket.IO -> browser | `src/websocket/server.py` |
| **api** | FastAPI gateway — REST + WebSocket, lifespan wires all services | `src/main.py` |
| **web** | Next.js 15 dashboard — spectator view, leaderboards, replay viewer | `src/app/page.tsx` |
| **replay** | Langfuse trace replay generation | (scaffolded) |
| **research** | GitHub/arXiv aggregator for agents | `src/aggregator/sweep.py` |

---

## Tournament Lifecycle (The Core Loop)

```
CREATE → PREP → RESEARCH → ARCHITECTURE → BUILD → CROSS_REVIEW → FIX → JUDGE → COMPLETE
```

### Phase-by-Phase Breakdown

| Phase | Duration (Duel) | What Happens |
|-------|-----------------|-------------|
| **PREP** | 5 min | Orchestrator creates Docker MicroVM sandboxes per team, spawns agent teams (3-8 agents each), delivers `CHALLENGE.md` into each sandbox |
| **RESEARCH** | 30 min | Researcher agent searches GitHub/arXiv/web for patterns. Architect reads challenge. Output: `RESEARCH.md` |
| **ARCHITECTURE** | 15 min | Architect creates `ARCHITECTURE.md`, project `CLAUDE.md`, `.claude/rules/`, decomposes work into tasks, sends task_assignments via Redis mailbox |
| **BUILD** | 60-90 min | All agents work in parallel. Builder writes code, Tester writes tests, Frontend builds UI, Critic reviews. Communication via Redis mailbox |
| **CROSS_REVIEW** | 15 min | Orchestrator grants read-only symlink to opponent's workspace. Critic reviews opponent's code. Structured review doc produced |
| **FIX** | 15 min | Teams fix issues from cross-review feedback. Last chance before judging |
| **JUDGE** | 10 min | Automated judges (pytest, ruff, mypy, coverage) + LLM judges (UX, architecture, innovation) score both teams in parallel |
| **COMPLETE** | — | ELO updated, sandboxes destroyed, results published |

Phase transitions are **enforced by timers** — when time runs out, the orchestrator force-transitions to the next phase with a 60-second warning.

---

## Agent Team Architecture

### 6 Agent Roles

| Role | Model | Responsibility | Key Tools |
|------|-------|---------------|-----------|
| **Architect** | Opus 4.6 | Team lead. System design, task decomposition, conflict resolution, project bootstrap (creates CLAUDE.md, rules, hooks) | read, write, bash, web_search, web_fetch |
| **Builder** | Opus/Sonnet 4.6 | Core backend engineer. Writes 60% of code: APIs, services, models | read, write(src/), bash(python/pytest/pip/ruff/mypy), web_search |
| **Frontend** | Sonnet 4.6 | Frontend engineer. React/Next.js components, styling | read, write(src/), bash |
| **Tester** | Haiku 4.5 | QA engineer. Tests, coverage, CI setup. Can block task_complete | read, write(tests/), bash(pytest/coverage) |
| **Critic** | Opus 4.6 | Adversarial reviewer. Reviews own team + cross-reviews opponent | read, bash(pytest/ruff/mypy/grep/git diff) — NO write |
| **Researcher** | Sonnet 4.6 | Real-time intelligence. GitHub, arXiv, web, package discovery | web_search, web_fetch, curl, read, write(RESEARCH.md) |

### Self-Configuration (Agents Creating Agent Configs)

The Architect agent **bootstraps the project's own `.claude/` configuration** inside the sandbox:

```
/arena/team-{id}/project/
├── CLAUDE.md              ← Architect creates this
├── .claude/
│   ├── rules/             ← Stack-specific coding standards
│   ├── hooks/             ← Auto-formatting, linting
│   ├── skills/            ← Custom skills for the challenge
│   └── agents/            ← Sub-agent definitions
├── ARCHITECTURE.md
└── src/
```

This is the "agents writing their own agent configs" capability — each project the team builds gets tailored Claude Code configuration.

---

## Communication: Redis Mailbox Protocol

Agents communicate via **Redis-backed mailboxes** (LPUSH/BRPOP for atomic message delivery):

```
mailbox:{team_id}:{role}  ←  Redis list (one per agent)
```

### Message Format

```json
{
  "from": "architect",
  "to": "builder",
  "type": "task_assignment",
  "priority": "high",
  "correlation_id": "uuid",
  "payload": { ... }
}
```

### 9 Message Types

| Type | From | To | Purpose |
|------|------|----|---------|
| `task_assignment` | Architect | Any | Assign work |
| `task_complete` | Any | Architect | Report completion |
| `review_request` | Any | Critic | Request code review |
| `review_feedback` | Critic | Any | Review results |
| `bug_report` | Tester/Critic | Builder/Frontend | Report issue |
| `architecture_update` | Architect | All | Design change |
| `help_request` | Any | Any | Ask for assistance |
| `status_update` | Any | Architect | Progress report |
| `conflict_resolution` | Architect | Any | Resolve disagreements |

### Agent Run Loop

```python
while agent.status not in (TERMINATED, ERROR):
    message = await mailbox.receive(role, timeout=5.0)  # BRPOP
    if message:
        await process_message(message)  # → LLM call → action
    agent.last_heartbeat = now()  # heartbeat every 5s
```

---

## Event Bus (Redis Streams)

**All state changes** publish immutable events to a single Redis Stream (`arena:events`):

```python
await event_bus.publish("tournament.phase.changed", payload={...})
```

Events are also published to **Redis Pub/Sub** for real-time spectator streaming.

### Key Event Types

```
tournament.created / .started / .completed / .cancelled
tournament.phase.changed / .phase.ending
tournament.team.spawned / .team.{event_type}
tournament.match.judged
tournament.agent.unresponsive
tournament.budget.warning
```

### Consumer Groups

Services subscribe with **glob patterns** and consumer groups for reliable delivery:

```python
@event_bus.subscribe("tournament.*")
async def handle(event: ArenaEvent): ...
```

### Event Schema

```python
class ArenaEvent(BaseModel):
    event_id: UUID
    event_type: str          # "tournament.match.started"
    timestamp: datetime      # UTC always
    version: int = 1         # Schema version for evolution
    source: str              # "core.tournament_orchestrator"
    correlation_id: UUID     # Links related events across services
    tournament_id: UUID | None
    team_id: UUID | None
    agent_id: UUID | None
    payload: dict
```

---

## Sandbox / MicroVM Isolation (5-Layer Security)

```
┌─ Layer 5: Parry Injection Scanner (real-time) ──────────────────┐
│ ┌─ Layer 4: AgentShield (102 rules, pre-execution scan) ──────┐ │
│ │ ┌─ Layer 3: Resource Limits (4GB RAM, 2 CPU, 10GB disk) ──┐ │ │
│ │ │ ┌─ Layer 2: Network Isolation (allowlist only) ────────┐ │ │ │
│ │ │ │ ┌─ Layer 1: Docker MicroVM (kernel isolation) ─────┐ │ │ │ │
│ │ │ │ │                                                   │ │ │ │ │
│ │ │ │ │   /arena/team-{id}/project/   (team workspace)    │ │ │ │ │
│ │ │ │ │   /arena/team-{id}/opponent/  (cross-review only) │ │ │ │ │
│ │ │ │ │                                                   │ │ │ │ │
│ │ │ │ └───────────────────────────────────────────────────┘ │ │ │ │
│ │ │ └─ ALLOW: pypi.org, npmjs.org, github.com, anthropic ──┘ │ │
│ │ └─ DENY: * (everything else) ─────────────────────────────┘ │
│ └─ Scan: secrets, priv-esc, container escape, data exfil ────┘
└─ Scan: prompt injection in all tool I/O ──────────────────────┘
```

### Network Allowlist

```
ALLOW: pypi.org, registry.npmjs.org, github.com, api.github.com,
       api.anthropic.com, api.openai.com, arxiv.org
DENY:  * (everything else)
```

LLM calls go through the **LiteLLM proxy** — no direct API keys in sandboxes.

### Resource Limits (Per Team)

| Resource | Duel | Grand Prix |
|----------|------|-----------|
| RAM | 4GB | 8GB |
| CPU | 2 vCPU | 4 vCPU |
| Disk | 10GB | 10GB |
| Processes | 100 max | 100 max |
| Idle timeout | 90s | 90s |

---

## Judging Pipeline (6 Dimensions)

```
               ┌── Automated ──┐          ┌── LLM (Opus 4.6) ──┐
               │               │          │                      │
Team A ──→ ┌───┤ Functionality  │    ┌─────┤ UX/Design (15%)     │
           │   │ (pytest 30%)   │    │     │ Architecture (10%)   │
           │   │ Code Quality   │    │     │ Innovation (10%)     │
           │   │ (ruff+mypy 20%)│    │     └──────────────────────┘
           │   │ Coverage (15%) │    │
           │   └────────────────┘    │
           └─────────────────────────┘
                    ↓ parallel for both teams
              Total = Σ(score × weight)
              Winner = highest total (draw if <1pt difference)
              → ELO updated via Bradley-Terry MLE + bootstrap CI
```

### Scoring Weights

| Dimension | Weight | Judge Type | How |
|-----------|--------|-----------|-----|
| Functionality | 30% | Automated | Run hidden pytest suite against team's code |
| Code Quality | 20% | Automated | `ruff check` issues (−2 each) + `mypy` errors (−5 each) |
| Test Coverage | 15% | Automated | `coverage.py` line + branch coverage |
| UX/Design | 15% | LLM (Opus 4.6, temp=0) | Review frontend code for user flows, states, accessibility |
| Architecture | 10% | LLM (Opus 4.6, temp=0) | Review ARCHITECTURE.md + code structure |
| Innovation | 10% | LLM (Opus 4.6, temp=0) | Novel approaches, creative solutions, beyond-requirements features |

Per-challenge scoring overrides are loaded from `challenges/library/{id}/scoring_config.json`.

---

## ELO Rating System

Uses **Bradley-Terry Maximum Likelihood Estimation** (same methodology as LMSYS Chatbot Arena):

- `wins_matrix[i][j]` = times config i beat config j
- Ratings normalized to ELO scale (mean=1500, std~200)
- **Bootstrap confidence intervals** (1000 resamples, 95% CI)
- `win_probability(A, B) = 1 / (1 + 10^((B-A)/400))`

```python
# Core formula
def bradley_terry_mle(wins_matrix: np.ndarray) -> np.ndarray:
    # Maximize log-likelihood of observed wins
    # Normalize to ELO scale (mean=1500, std≈200)
```

---

## LLM Client (Model-Agnostic via LiteLLM)

All LLM calls go through `LLMClient` → **LiteLLM proxy** (OpenAI-compatible API):

| Model | Use Case | Cost/1M tokens (in/out) |
|-------|----------|------------------------|
| Opus 4.6 | Architect, Critic, Judge | $15 / $75 |
| Sonnet 4.6 | Builder, Researcher, Frontend | $3 / $15 |
| Haiku 4.5 | Tester (speed) | $0.80 / $4 |
| GPT-5 | Alternative for teams | $10 / $30 |
| Gemini 3 Pro | Alternative for teams | $3.50 / $10.50 |
| Qwen3-72B | Alternative for teams | $0.90 / $0.90 |
| Qwen3-32B | Alternative for teams | $0.40 / $0.40 |
| Qwen3-8B | Alternative for teams | $0.20 / $0.20 |

Every call is **traced via Langfuse** with agent_id, team_id, and message_type metadata.

### Budget Controls

- Per-tournament budget limit (default $500, max $5000)
- Alert at 80% threshold
- Health monitor checks budget every 30 seconds
- Exceeding budget force-ends BUILD phase

---

## Real-Time Spectator Pipeline

```
Agent Action → Redis Pub/Sub → SpectatorServer → Socket.IO → Browser
                                      ↓
                               Tutor AI (Haiku 4.5)
                                      ↓
                               Commentary → Browser
```

### Spectator Features

- Join a `tournament:{id}` room for live event streaming
- Agent status updates (role, status, detail)
- Tutor commentary (AI-generated insights on what agents are doing)
- Code diffs via Monaco Editor
- Terminal output via xterm.js
- ELO charts via D3/Recharts

### Latency Target: <100ms from agent action to spectator screen

---

## Tournament Formats

| Format | Teams | Rounds | Build Time | Total Duration |
|--------|-------|--------|-----------|---------------|
| **Duel** | 2 | 1 | 90 min | ~3 hours |
| **Standard** | 4-8 | log2(n) (single elimination) | 75 min | ~5 hours |
| **League** | 3-8 | n-1 (round-robin) | 60 min | ~8 hours |
| **Grand Prix** | 4-16 | Swiss system (~log2(n)+1) | 45 min | ~6 hours |

---

## Challenge Library

Challenges live in `challenges/library/{id}/`:

```
challenges/library/realtime-chat-app/
├── CHALLENGE.md            ← Brief delivered to teams
├── scoring_config.json     ← Weight overrides for this challenge
└── hidden_tests/           ← Pytest suite run by judge (teams never see this)
    ├── conftest.py
    ├── test_websocket.py
    ├── test_rooms.py
    └── test_persistence.py
```

### Existing Challenges

| Challenge | Category | Difficulty |
|-----------|----------|-----------|
| `realtime-chat-app` | Real-Time | Medium |
| `task-queue-engine` | API Service | Medium |
| `url-shortener-saas` | SaaS App | Easy |

---

## Infrastructure (docker-compose)

| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL 16 | 5432 | Relational data (tournaments, teams, matches) |
| Redis 7 | 6379 | Event bus (Streams), agent mailboxes (Lists), cache, Pub/Sub |
| LiteLLM proxy | 4000 | Model-agnostic LLM gateway |
| MinIO | 9000 | Object storage (artifacts, replays) |
| Langfuse | 3001 | LLM tracing and observability |
| Qdrant | 6333 | Vector search |
| FastAPI | 8000 | API gateway |
| Next.js | 3000 | Web dashboard |

---

## Service Initialization (Dependency Graph)

On startup (`packages/api/src/main.py` lifespan), services are wired in order:

```
1. Database (PostgreSQL via SQLAlchemy async)
2. Redis (aioredis)
3. EventBus (wraps Redis Streams)
4. Langfuse (optional tracing)
5. LLMClient (wraps LiteLLM proxy + Langfuse)
6. SandboxManager (Docker MicroVM lifecycle)
7. AgentTeamManager (agent spawn/teardown, needs EventBus + Redis + LLMClient)
8. JudgeService (needs EventBus + SandboxManager + LLMClient)
9. TournamentOrchestrator (needs EventBus + SandboxManager + AgentTeamManager + JudgeService)
```

On shutdown: teardown agents → destroy sandboxes → close LLM client → flush Langfuse → close Redis → close DB.

---

## Data Flow Summary

```
User creates tournament (API)
  → TournamentOrchestrator.create_tournament()
    → Persist to PostgreSQL
    → Publish "tournament.created" to Redis Streams

User starts tournament
  → SandboxManager.create_sandbox() per team (Docker MicroVM)
  → AgentTeamManager.spawn_team() per team
    → Create RedisMailbox per team
    → Start AgentProcess per role (asyncio tasks)
    → Each agent enters BRPOP loop on their mailbox
  → Deliver CHALLENGE.md to sandboxes
  → Transition to RESEARCH phase (start phase timer)

Phase timer ticks → force transition → agents notified via events
Health monitor (every 30s) → check heartbeats + budget

BUILD phase → agents communicate via mailbox → LLM calls via LiteLLM proxy
CROSS_REVIEW → read-only symlink to opponent workspace
JUDGE → AutomatedJudge (pytest/ruff/coverage) + LLMJudge (Opus 4.6) → MatchResult
COMPLETE → ELO update → sandbox teardown → event published

All events → SpectatorServer → Socket.IO → Next.js dashboard
All LLM calls → Langfuse tracing → replay generation
```

---

## Existing Tournament Artifact

There's a completed duel (`tournaments/duel-001-realtime-chat/`) with two teams (Alpha and Bravo) that built a realtime chat app. Both teams have full project structures with source code, tests, ADRs, and their own `.claude/` configurations — demonstrating the full self-configuration flow working end-to-end.

### Team Alpha Structure

```
team-alpha/
├── CLAUDE.md, ARCHITECTURE.md, README.md
├── .claude/agents/ (architect.md, tester.md)
├── .claude/rules/ (global, code-quality, testing, architecture)
├── .claude/skills/websocket-chat/
├── .claude/memory/ (decisions-log, gotchas)
├── docs/decisions/ (3 ADRs)
├── src/ (main, config, database, models, messages, rooms, presence, websocket_manager)
└── tests/ (messages, rooms, presence, websocket)
```

### Team Bravo Structure

```
team-bravo/
├── CLAUDE.md, ARCHITECTURE.md, README.md
├── .claude/agents/ (builder.md, reviewer.md)
├── .claude/rules/ (global, code-quality, testing, websocket)
├── .claude/skills/realtime-messaging/
├── .claude/memory/ (decisions-log, gotchas)
├── docs/decisions/ (3 ADRs)
├── src/ (main, config, database, models, messages, rooms, presence, websocket_manager)
└── tests/ (messages, rooms, presence, websocket)
```
