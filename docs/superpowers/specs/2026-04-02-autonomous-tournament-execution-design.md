# Autonomous Tournament Execution — Design Spec

> **Date:** 2026-04-02
> **Status:** Draft
> **Problem:** Tournaments currently produce fake competitions. Agents are LLM wrappers that receive messages but have no behavior. Projects are identical because a human writes both.

## 1. Problem Statement

The Arena's current agent system (`AgentProcess` in `packages/agents/src/teams/manager.py`) is a Redis mailbox + LLM completion wrapper. When a message arrives, it sends the message to an LLM and... does nothing with the response. There is:

- No file writing capability
- No bash execution
- No project bootstrapping
- No inter-agent task coordination
- No self-configuration
- No RALPH self-healing loop

The `ProjectBootstrapper` exists but is never called. The `.claude/agents/*.md` system prompt files don't exist. The result: tournaments produce empty sandboxes.

## 2. Design: Claude Code CLI as Agent Runtime

### Core Change

Replace the `AgentProcess` LLM-wrapper with a `ClaudeCodeRunner` that spawns an **actual Claude Code CLI process** inside each team's Docker sandbox. Each team gets one autonomous Claude Code session that:

1. Reads `CHALLENGE.md` (delivered by orchestrator)
2. Self-configures (creates its own CLAUDE.md, rules, hooks, skills)
3. Architectures the solution
4. Builds the project with real file writes and bash commands
5. Runs tests and self-heals (RALPH loop)
6. Produces a runnable application

### Why One CLI Per Team (Not Multiple Agents)

The multi-agent mailbox design (architect, builder, tester, critic) adds complexity without value when the underlying runtime is Claude Code. Claude Code already:
- Plans before coding
- Runs tests and fixes failures
- Self-corrects based on errors
- Manages file writes and bash execution

One CLI session per team is simpler, more reliable, and produces better results. The "team of agents" concept becomes a **strategy configuration** that shapes the system prompt, not separate processes.

## 3. Architecture

```
Orchestrator
    │
    ├─── Team Alpha Sandbox (Docker MicroVM)
    │       └── claude CLI process
    │            ├── reads: CHALLENGE.md, strategy.json
    │            ├── creates: CLAUDE.md, .claude/*, src/*, tests/*
    │            ├── streams: stdout → Redis Pub/Sub → Spectator WebSocket
    │            └── env: ANTHROPIC_API_KEY (via LiteLLM proxy)
    │
    ├─── Team Bravo Sandbox (Docker MicroVM)
    │       └── claude CLI process
    │            └── (same as above, different strategy)
    │
    └─── Judge (runs AFTER both teams finish or time expires)
            ├── copies team outputs to judge workspace
            ├── runs hidden test suite
            ├── runs ruff + mypy
            ├── LLM scores architecture + UX + innovation
            └── publishes scores + winner
```

### New Module: `ClaudeCodeRunner`

**Location:** `packages/agents/src/runner/claude_code.py`

```python
class ClaudeCodeRunner:
    """Runs an actual Claude Code CLI session inside a team's sandbox."""

    def __init__(
        self,
        team_id: UUID,
        workspace_path: str,
        strategy: TeamStrategy,
        event_bus: EventBus,
        api_base_url: str,      # LiteLLM proxy URL
        model: str = "claude-sonnet-4-6",
    ) -> None: ...

    async def start(self, challenge_path: str) -> None:
        """Start Claude Code CLI with the challenge as initial prompt."""
        # 1. Write strategy-specific system prompt to workspace
        # 2. Write CLAUDE.md seed (minimal — CLI will expand it)
        # 3. Spawn: claude --dangerously-skip-permissions \
        #           --model {model} \
        #           --print \
        #           --output-format stream-json \
        #           -p "{initial_prompt}"
        # 4. Stream stdout line-by-line → parse JSON events
        # 5. Forward events to Redis Pub/Sub for spectator

    async def stream_output(self) -> AsyncIterator[AgentEvent]:
        """Yield parsed events from Claude Code's stream-json output."""

    async def stop(self) -> None:
        """Send SIGTERM, wait 10s, SIGKILL if needed."""

    async def get_status(self) -> RunnerStatus:
        """Check if CLI process is still running, get token/cost stats."""
```

### Initial Prompt (Delivered to Claude Code)

The prompt is the key differentiator between teams. It combines:
1. **Challenge brief** (same for all teams)
2. **Strategy config** (different per team — architecture-first vs TDD-first vs speed-run)
3. **Self-configuration instructions** (create your own CLAUDE.md, rules, hooks)
4. **RALPH instructions** (run tests, fix failures, iterate)
5. **Time awareness** (you have N minutes for this phase)

```python
INITIAL_PROMPT_TEMPLATE = """
You are an autonomous AI agent competing in AgentForge Arena.

## Challenge
{challenge_brief}

## Your Strategy
{strategy_description}

## Phase: {current_phase} ({time_limit} minutes)

## Instructions
1. Read CHALLENGE.md carefully
2. Create your project's CLAUDE.md with architecture decisions
3. Create .claude/rules/ for your stack's coding standards
4. Create .claude/hooks/post-write.sh for auto-formatting
5. Build the complete application:
   - Design the architecture first (ARCHITECTURE.md)
   - Implement all features specified in the challenge
   - Write comprehensive tests (target 80%+ coverage)
   - Ensure the app runs: uvicorn src.main:app --port 8000
6. RALPH Loop: After each major feature, run tests. If they fail, fix them.
   Do NOT move on to the next feature until current tests pass.
7. When done, ensure `pytest` passes and the server starts clean.

## Constraints
- Python 3.12, FastAPI, Pydantic v2
- All code in src/, tests in tests/
- Must have: pyproject.toml, Dockerfile, README.md, ARCHITECTURE.md
- Must pass: ruff check . && pytest
"""
```

### Strategy Configs

Replace the current `TeamConfig.agents[]` (list of agent roles) with `TeamStrategy`:

```python
class TeamStrategy(BaseModel):
    name: str                          # "architecture-first", "tdd-first", "speed-run"
    description: str                   # Human-readable strategy description
    model: str = "claude-sonnet-4-6"   # Model for this team's CLI
    approach: Literal["architecture_first", "tdd_first", "speed_run", "balanced"]
    priorities: list[str]              # Ordered: ["architecture", "tests", "features", "docs"]
    time_allocation: dict[str, float]  # Phase → percentage of time
    rules: list[str]                   # Extra rules injected into CLAUDE.md
```

**Built-in strategies:**

| Strategy | Model | Approach | Key Trait |
|----------|-------|----------|-----------|
| `architecture-first` | Opus | Design before code | Writes ARCHITECTURE.md + ADRs first, then implements |
| `tdd-first` | Sonnet | Tests before features | Writes test stubs first, then makes them pass |
| `speed-run` | Sonnet | Ship fast, fix later | Implements features first, adds tests after |
| `balanced` | Sonnet | Equal time on all | Alternates between design, code, and tests |

### Output Streaming (Spectator Integration)

Claude Code's `--output-format stream-json` emits structured events:

```json
{"type": "assistant", "message": {"content": [{"type": "text", "text": "..."}]}}
{"type": "tool_use", "name": "Write", "input": {"file_path": "...", "content": "..."}}
{"type": "tool_result", "content": "File written successfully"}
```

The `ClaudeCodeRunner.stream_output()` parses these and publishes to Redis Pub/Sub:

```python
# Event types published to spectator
"agent.tool.write"      # File created/modified (path + diff)
"agent.tool.bash"       # Command executed (cmd + output snippet)
"agent.tool.read"       # File read (path only)
"agent.thinking"        # Assistant reasoning (summary, not full)
"agent.progress"        # Milestone reached (e.g., "tests passing: 12/15")
```

## 4. Orchestrator Changes

### Current Flow (Broken)
```
create_tournament → start_tournament → spawn_team (N agents per team)
    → deliver_challenge → phase_timer → agents sit idle → judge empty projects
```

### New Flow
```
create_tournament → start_tournament → create_sandboxes
    → write CHALLENGE.md + strategy.json into each sandbox
    → start ClaudeCodeRunner per team (parallel)
    → stream events to spectator
    → phase_timer enforces deadlines (SIGTERM on timeout)
    → judge: copy outputs, run hidden tests, score
    → publish results
```

### Key Changes to `orchestrator.py`

1. **Replace `agent_manager: AgentTeamManager`** with `runner_manager: RunnerManager`
2. **`start_tournament()`**: Instead of `spawn_team()`, call `runner_manager.start_team(team_id, strategy, challenge_path)`
3. **Phase transitions simplified**: No need to notify agents of phase changes — the initial prompt includes time awareness. The orchestrator just enforces the deadline.
4. **`_execute_phase_setup(BUILD)`**: Start the Claude Code CLI
5. **`_execute_phase_setup(JUDGE)`**: Stop all CLIs, invoke judge
6. **Simplified phases**: Merge RESEARCH + ARCHITECTURE + BUILD into one BUILD phase. The strategy config tells the CLI how to allocate time internally. This eliminates the problem of "how do we tell a running CLI to switch phases."

### Simplified Phase Machine

```
PREP → BUILD → CROSS_REVIEW → FIX → JUDGE → COMPLETE
```

- **PREP** (2 min): Create sandboxes, write challenge
- **BUILD** (configurable, default 30 min for duel): Claude Code runs autonomously
- **CROSS_REVIEW** (10 min): Each team's CLI gets read access to opponent + review prompt
- **FIX** (10 min): CLI addresses review feedback
- **JUDGE** (5 min): Automated scoring
- **COMPLETE**: Results published

## 5. Sandbox Changes

### Current
`SandboxManager.create_sandbox()` runs `docker sandbox create claude` — this is correct and stays.

### New Requirements

1. **Environment injection**: Pass `ANTHROPIC_API_KEY` (or LiteLLM proxy URL) into sandbox
2. **Claude Code pre-install**: Base sandbox image must have `claude` CLI installed
3. **Port mapping**: Each sandbox exposes port 8000 for the app server (mapped to unique host port)
4. **stdout capture**: `ClaudeCodeRunner` reads the CLI process's stdout in real-time

### Updated `_initialize_workspace()`

Add:
- Write `CHALLENGE.md` (challenge brief)
- Write `strategy.json` (team strategy config)
- Write `.claude/settings.json` (Claude Code settings: model, permissions)
- Pre-create `src/`, `tests/`, `.claude/rules/`, `.claude/hooks/`

## 6. Judge Changes

### Current
`JudgeService` already has 6 scoring dimensions. Keep all of them.

### New
1. **Hidden test injection**: Before judging, copy hidden test files from `challenges/library/{id}/hidden_tests/` into each team's workspace
2. **Server health check**: Before scoring, verify the team's app starts on port 8000 (`httpx.get("http://localhost:{port}/health")`)
3. **Score persistence**: Write scores to database (currently in-memory only)
4. **Cross-review score**: Add 7th dimension — score from opponent team's review

## 7. Bootstrap Changes

### Current
`ProjectBootstrapper` generates 11 template files but is never called.

### New Role
The bootstrapper becomes **optional seed content**. The Claude Code CLI is told to self-configure, but we pre-seed minimal files to help it start faster:

1. **Always written by orchestrator**: `CHALLENGE.md`, `strategy.json`
2. **Optionally pre-seeded** (can be overwritten by CLI): minimal `CLAUDE.md` with challenge context
3. **Created by Claude Code CLI**: Everything else (architecture, code, tests, hooks, rules)

This means the CLI genuinely creates its own project infrastructure. The pre-seed is a hint, not a constraint.

## 8. File Changes Summary

| File | Action | What Changes |
|------|--------|-------------|
| `packages/agents/src/runner/claude_code.py` | **NEW** | ClaudeCodeRunner — spawns and manages Claude Code CLI |
| `packages/agents/src/runner/manager.py` | **NEW** | RunnerManager — manages multiple ClaudeCodeRunners |
| `packages/agents/src/runner/strategies.py` | **NEW** | Built-in strategy definitions |
| `packages/agents/src/runner/prompt.py` | **NEW** | Initial prompt template builder |
| `packages/agents/src/runner/stream_parser.py` | **NEW** | Parses Claude Code stream-json output |
| `packages/core/src/tournament/orchestrator.py` | **MODIFY** | Replace agent_manager with runner_manager, simplify phases |
| `packages/sandbox/src/docker/manager.py` | **MODIFY** | Add env injection, port mapping, Claude CLI pre-install check |
| `packages/judge/src/scoring/service.py` | **MODIFY** | Add hidden test injection, server health check, score persistence |
| `packages/shared/src/types/models.py` | **MODIFY** | Add TeamStrategy, RunnerStatus, simplify TournamentPhase enum |
| `packages/agents/CLAUDE.md` | **MODIFY** | Document new runner architecture |
| `packages/core/CLAUDE.md` | **MODIFY** | Document simplified phase machine |
| `CLAUDE.md` (root) | **MODIFY** | Update architecture overview |
| `challenges/library/realtime-chat/CHALLENGE.md` | **NEW** | First real challenge with hidden tests |
| `challenges/library/realtime-chat/hidden_tests/` | **NEW** | pytest files the judge runs |

## 9. What We Keep

- **Event bus** (Redis Streams) — works perfectly, no changes
- **Spectator WebSocket** — works, just needs new event types from stream parser
- **Judge scoring** (6 dimensions) — works, add hidden test injection
- **ELO calculator** — works, no changes
- **Sandbox creation** (`docker sandbox create claude`) — works, minor additions
- **Redis mailbox** — keep for future multi-agent experiments, not used in v1

## 10. What We Remove

- `AgentProcess._process_message()` LLM wrapper — replaced by Claude Code CLI
- `AgentTeamManager.spawn_team()` multi-agent spawning — replaced by `RunnerManager.start_team()`
- Complex phase transitions (RESEARCH → ARCHITECTURE → BUILD) — merged into single BUILD phase
- `AGENT_PROMPT_FILES` mapping — replaced by strategy-based prompt generation

## 11. Challenge Format

Each challenge in `challenges/library/{id}/` contains:

```
challenges/library/realtime-chat/
├── CHALLENGE.md              # Brief shown to teams
├── hidden_tests/
│   ├── conftest.py           # Test fixtures (httpx client, WebSocket helpers)
│   ├── test_rooms.py         # Room CRUD tests
│   ├── test_messages.py      # Message persistence tests
│   ├── test_websocket.py     # WebSocket connection tests
│   └── test_edge_cases.py    # Error handling, concurrency
├── scoring_config.json       # Weight overrides for this challenge
└── metadata.json             # Category, difficulty, time estimates
```

## 12. Security Model

No changes to the 5-layer security model. Claude Code CLI runs inside the Docker sandbox with:
- Kernel isolation (MicroVM)
- Network allow/deny (pypi, npm, github, anthropic API only)
- Resource limits (4GB RAM, 2 CPU)
- `--dangerously-skip-permissions` flag (safe inside sandbox — the sandbox IS the permission boundary)

The `ANTHROPIC_API_KEY` is passed as an environment variable inside the sandbox. In production, this routes through LiteLLM proxy with per-team budget caps.

## 13. Live Demo Flow

After implementation, a tournament looks like this:

```bash
# Terminal 1: Start the platform
make dev

# Terminal 2: Create and start a duel
curl -X POST http://localhost:8000/api/v1/tournaments \
  -H "Content-Type: application/json" \
  -d '{
    "format": "duel",
    "challenge_id": "realtime-chat",
    "teams": [
      {"name": "Alpha", "strategy": "architecture-first"},
      {"name": "Bravo", "strategy": "tdd-first"}
    ],
    "build_time_minutes": 30
  }'

# Terminal 3: Watch live
open http://localhost:3000/arena/{tournament_id}

# After 30 min + judging:
# - Team Alpha's app runs on http://localhost:8001
# - Team Bravo's app runs on http://localhost:8002
# - Scores at http://localhost:3000/arena/{tournament_id}/results
```

## 14. Implementation Order

1. **Challenge library** — Create first real challenge with hidden tests
2. **ClaudeCodeRunner** — Core new module, spawn + stream + stop
3. **RunnerManager** — Manage multiple runners, integrate with orchestrator
4. **Orchestrator refactor** — Simplified phases, use RunnerManager
5. **Sandbox updates** — Env injection, port mapping
6. **Judge updates** — Hidden test injection, server health check
7. **Spectator updates** — Parse stream-json events, forward to WebSocket
8. **Strategy definitions** — Built-in strategies with distinct prompts
9. **API route updates** — Accept strategy in tournament creation
10. **Integration test** — End-to-end tournament with real Claude Code CLI
