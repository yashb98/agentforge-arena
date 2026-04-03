# Autonomous Tournament Execution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Arena tournaments spawn real Claude Code CLI sessions that autonomously build projects inside Docker sandboxes, replacing the current do-nothing LLM-wrapper agents.

**Architecture:** Each team gets one Claude Code CLI process running inside a Docker sandbox MicroVM. The CLI reads a challenge brief, self-configures (CLAUDE.md, rules, hooks), builds a complete application, and streams every action to spectators. A judge runs hidden tests against the finished projects.

**Tech Stack:** Python 3.12, FastAPI, Claude Code CLI (`claude` binary), Docker sandbox, Redis Streams/Pub-Sub, asyncio subprocess, pytest (judge)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `packages/agents/src/runner/__init__.py` | Package init |
| `packages/agents/src/runner/claude_code.py` | `ClaudeCodeRunner` — spawns and manages one Claude Code CLI process |
| `packages/agents/src/runner/manager.py` | `RunnerManager` — manages multiple ClaudeCodeRunners across teams |
| `packages/agents/src/runner/strategies.py` | Built-in strategy definitions (architecture-first, tdd-first, speed-run) |
| `packages/agents/src/runner/prompt.py` | Builds the initial prompt from challenge + strategy |
| `packages/agents/src/runner/stream_parser.py` | Parses Claude Code `--output-format stream-json` into typed events |
| `packages/shared/src/types/models.py` | Add `TeamStrategy`, `RunnerStatus`, `RunnerEvent` models |
| `packages/core/src/tournament/orchestrator.py` | Replace agent_manager with runner_manager, simplify phases |
| `packages/sandbox/src/docker/manager.py` | Add port mapping and env injection |
| `packages/judge/src/scoring/service.py` | Add hidden test file copying into workspace before judging |
| `challenges/library/realtime-chat/CHALLENGE.md` | First real challenge brief |
| `challenges/library/realtime-chat/hidden_tests/conftest.py` | Test fixtures for judge |
| `challenges/library/realtime-chat/hidden_tests/test_api.py` | Hidden API tests |
| `challenges/library/realtime-chat/hidden_tests/test_websocket.py` | Hidden WebSocket tests |
| `challenges/library/realtime-chat/metadata.json` | Challenge metadata |
| `challenges/library/realtime-chat/scoring_config.json` | Weight overrides |
| `packages/api/src/routes/tournaments.py` | Accept strategy-based team config |
| `packages/agents/tests/runner/test_claude_code.py` | Unit tests for ClaudeCodeRunner |
| `packages/agents/tests/runner/test_stream_parser.py` | Unit tests for stream parser |
| `packages/agents/tests/runner/test_strategies.py` | Unit tests for strategy definitions |
| `packages/agents/tests/runner/test_prompt.py` | Unit tests for prompt builder |
| `packages/core/tests/test_orchestrator_v2.py` | Integration tests for new orchestrator flow |

---

### Task 1: Add New Types to Shared Models

**Files:**
- Modify: `packages/shared/src/types/models.py`
- Test: `packages/shared/tests/test_models.py` (create if missing)

- [ ] **Step 1: Write tests for new models**

Create `packages/shared/tests/test_new_models.py`:

```python
"""Tests for new tournament execution types."""
from __future__ import annotations

import pytest
from packages.shared.src.types.models import (
    RunnerEvent,
    RunnerStatus,
    TeamStrategy,
    TournamentPhase,
)


def test_team_strategy_defaults():
    """Default strategy is balanced with sonnet."""
    s = TeamStrategy(name="test-team")
    assert s.approach == "balanced"
    assert s.model == "claude-sonnet-4-6"


def test_team_strategy_validates_approach():
    """Only valid approaches accepted."""
    s = TeamStrategy(name="alpha", approach="architecture_first")
    assert s.approach == "architecture_first"
    with pytest.raises(Exception):
        TeamStrategy(name="bad", approach="invalid_approach")


def test_runner_status_defaults():
    """Runner starts as pending with zero tokens."""
    rs = RunnerStatus(team_id="abc")
    assert rs.is_running is False
    assert rs.total_tokens == 0
    assert rs.exit_code is None


def test_runner_event_tool_use():
    """RunnerEvent captures tool use events."""
    e = RunnerEvent(
        event_type="tool_use",
        tool_name="Write",
        tool_input={"file_path": "src/main.py"},
    )
    assert e.event_type == "tool_use"
    assert e.tool_name == "Write"


def test_simplified_phase_enum():
    """TournamentPhase includes BUILD (merged from research+architecture+build)."""
    assert TournamentPhase.PREP.value == "prep"
    assert TournamentPhase.BUILD.value == "build"
    assert TournamentPhase.JUDGE.value == "judge"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yashbishnoi/Downloads/agentforge-arena && python -m pytest packages/shared/tests/test_new_models.py -v`
Expected: FAIL — `TeamStrategy`, `RunnerStatus`, `RunnerEvent` not defined

- [ ] **Step 3: Add new models to shared types**

Add to `packages/shared/src/types/models.py` after the `LeaderboardEntry` class (after line 308):

```python
# ============================================================
# Runner Types (Claude Code CLI execution)
# ============================================================


class TeamStrategy(BaseModel):
    """Strategy configuration for a team's Claude Code CLI session."""

    model_config = ConfigDict(strict=True)

    name: str = Field(min_length=1, max_length=100, description="Team display name")
    approach: str = Field(
        default="balanced",
        pattern=r"^(architecture_first|tdd_first|speed_run|balanced)$",
        description="Development approach that shapes the initial prompt",
    )
    model: str = Field(
        default="claude-sonnet-4-6",
        description="Claude model for this team's CLI session",
    )
    priorities: list[str] = Field(
        default_factory=lambda: ["architecture", "features", "tests", "docs"],
        description="Ordered priority list for the agent",
    )
    extra_rules: list[str] = Field(
        default_factory=list,
        description="Additional rules injected into the agent's CLAUDE.md",
    )
    sandbox_memory: str = Field(default="4g", description="Docker sandbox memory limit")
    sandbox_cpus: int = Field(default=2, ge=1, le=8, description="Docker sandbox CPU count")


class RunnerStatus(BaseModel):
    """Status of a running Claude Code CLI process."""

    team_id: str
    is_running: bool = False
    pid: int | None = None
    exit_code: int | None = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    files_written: int = 0
    commands_run: int = 0
    started_at: datetime | None = None
    last_event_at: datetime | None = None


class RunnerEvent(BaseModel):
    """A parsed event from Claude Code's stream-json output."""

    event_type: str = Field(description="assistant | tool_use | tool_result | error | system")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tool_name: str | None = None
    tool_input: dict[str, object] | None = None
    content: str | None = None
    error: str | None = None
```

Also update `TournamentConfig` (line 131-140) to accept strategies instead of agent configs:

Replace the existing `TournamentConfig`:
```python
class TournamentConfig(BaseModel):
    """Configuration for creating a tournament."""

    model_config = ConfigDict(strict=True)

    format: TournamentFormat
    challenge_id: str | None = None
    teams: list[TeamStrategy] = Field(min_length=2, max_length=8)
    build_time_minutes: int = Field(default=30, ge=5, le=180, description="Minutes for BUILD phase")
    budget_limit_usd: float = Field(default=500.0, ge=10.0, le=5000.0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yashbishnoi/Downloads/agentforge-arena && python -m pytest packages/shared/tests/test_new_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
git add packages/shared/src/types/models.py packages/shared/tests/test_new_models.py
git commit -m "feat(shared): add TeamStrategy, RunnerStatus, RunnerEvent models

Replace AgentConfig/TeamConfig with strategy-based team configuration.
TournamentConfig now accepts TeamStrategy instead of agent role lists."
```

---

### Task 2: Create Stream Parser

**Files:**
- Create: `packages/agents/src/runner/__init__.py`
- Create: `packages/agents/src/runner/stream_parser.py`
- Test: `packages/agents/tests/runner/test_stream_parser.py`

- [ ] **Step 1: Write tests for stream parser**

Create `packages/agents/tests/runner/__init__.py` (empty) and `packages/agents/tests/runner/test_stream_parser.py`:

```python
"""Tests for Claude Code stream-json parser."""
from __future__ import annotations

import json

import pytest
from packages.agents.src.runner.stream_parser import parse_stream_line, StreamParser


def test_parse_assistant_message():
    """Parse an assistant text message."""
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "I'll create the project structure."}]},
    })
    event = parse_stream_line(line)
    assert event is not None
    assert event.event_type == "assistant"
    assert "create the project" in event.content


def test_parse_tool_use():
    """Parse a tool use event."""
    line = json.dumps({
        "type": "tool_use",
        "name": "Write",
        "input": {"file_path": "/workspace/src/main.py", "content": "print('hello')"},
    })
    event = parse_stream_line(line)
    assert event is not None
    assert event.event_type == "tool_use"
    assert event.tool_name == "Write"
    assert event.tool_input["file_path"] == "/workspace/src/main.py"


def test_parse_tool_result():
    """Parse a tool result event."""
    line = json.dumps({
        "type": "tool_result",
        "content": "File written successfully",
    })
    event = parse_stream_line(line)
    assert event is not None
    assert event.event_type == "tool_result"
    assert "File written" in event.content


def test_parse_invalid_json_returns_none():
    """Invalid JSON lines are skipped."""
    assert parse_stream_line("not json") is None
    assert parse_stream_line("") is None


def test_parse_unknown_type_returns_generic():
    """Unknown event types are captured as generic events."""
    line = json.dumps({"type": "unknown_thing", "data": "hello"})
    event = parse_stream_line(line)
    assert event is not None
    assert event.event_type == "unknown_thing"


def test_stream_parser_tracks_stats():
    """StreamParser accumulates file and command counts."""
    parser = StreamParser()
    write_event = json.dumps({"type": "tool_use", "name": "Write", "input": {"file_path": "a.py", "content": "x"}})
    bash_event = json.dumps({"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}})

    parser.feed(write_event)
    parser.feed(bash_event)

    assert parser.files_written == 1
    assert parser.commands_run == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yashbishnoi/Downloads/agentforge-arena && python -m pytest packages/agents/tests/runner/test_stream_parser.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement stream parser**

Create `packages/agents/src/runner/__init__.py` (empty file).

Create `packages/agents/src/runner/stream_parser.py`:

```python
"""Parse Claude Code CLI stream-json output into typed events."""
from __future__ import annotations

import json
import logging

from packages.shared.src.types.models import RunnerEvent

logger = logging.getLogger(__name__)


def parse_stream_line(line: str) -> RunnerEvent | None:
    """Parse a single line of Claude Code stream-json output.

    Returns None for lines that cannot be parsed (empty, invalid JSON).
    """
    line = line.strip()
    if not line:
        return None

    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    event_type = data.get("type", "unknown")

    if event_type == "assistant":
        # Extract text content from assistant message
        message = data.get("message", {})
        content_blocks = message.get("content", [])
        text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
        return RunnerEvent(
            event_type="assistant",
            content="\n".join(text_parts) if text_parts else None,
        )

    if event_type == "tool_use":
        return RunnerEvent(
            event_type="tool_use",
            tool_name=data.get("name"),
            tool_input=data.get("input"),
        )

    if event_type == "tool_result":
        content = data.get("content", "")
        if isinstance(content, list):
            content = "\n".join(str(c) for c in content)
        return RunnerEvent(
            event_type="tool_result",
            content=str(content),
        )

    # Generic fallback for any other type
    return RunnerEvent(
        event_type=event_type,
        content=json.dumps(data),
    )


class StreamParser:
    """Stateful parser that tracks aggregate stats from a Claude Code session."""

    def __init__(self) -> None:
        self.files_written: int = 0
        self.commands_run: int = 0
        self.events: list[RunnerEvent] = []

    def feed(self, line: str) -> RunnerEvent | None:
        """Parse a line and update internal counters."""
        event = parse_stream_line(line)
        if event is None:
            return None

        self.events.append(event)

        if event.event_type == "tool_use" and event.tool_name:
            if event.tool_name in ("Write", "Edit"):
                self.files_written += 1
            elif event.tool_name == "Bash":
                self.commands_run += 1

        return event
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yashbishnoi/Downloads/agentforge-arena && python -m pytest packages/agents/tests/runner/test_stream_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
git add packages/agents/src/runner/ packages/agents/tests/runner/
git commit -m "feat(agents): add Claude Code stream-json parser

Parses assistant messages, tool_use, and tool_result events.
StreamParser tracks aggregate stats (files written, commands run)."
```

---

### Task 3: Create Strategy Definitions

**Files:**
- Create: `packages/agents/src/runner/strategies.py`
- Test: `packages/agents/tests/runner/test_strategies.py`

- [ ] **Step 1: Write tests**

Create `packages/agents/tests/runner/test_strategies.py`:

```python
"""Tests for built-in team strategies."""
from __future__ import annotations

import pytest
from packages.agents.src.runner.strategies import (
    BUILT_IN_STRATEGIES,
    get_strategy,
)
from packages.shared.src.types.models import TeamStrategy


def test_builtin_strategies_exist():
    """All four built-in strategies are defined."""
    assert "architecture-first" in BUILT_IN_STRATEGIES
    assert "tdd-first" in BUILT_IN_STRATEGIES
    assert "speed-run" in BUILT_IN_STRATEGIES
    assert "balanced" in BUILT_IN_STRATEGIES


def test_get_strategy_by_name():
    """get_strategy returns the named strategy."""
    s = get_strategy("architecture-first", team_name="Alpha")
    assert isinstance(s, TeamStrategy)
    assert s.approach == "architecture_first"
    assert s.name == "Alpha"


def test_get_strategy_unknown_falls_back_to_balanced():
    """Unknown strategy name falls back to balanced."""
    s = get_strategy("nonexistent", team_name="Fallback")
    assert s.approach == "balanced"


def test_architecture_first_priorities():
    """Architecture-first strategy prioritizes architecture."""
    s = get_strategy("architecture-first", team_name="A")
    assert s.priorities[0] == "architecture"


def test_tdd_first_priorities():
    """TDD-first strategy prioritizes tests."""
    s = get_strategy("tdd-first", team_name="B")
    assert s.priorities[0] == "tests"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yashbishnoi/Downloads/agentforge-arena && python -m pytest packages/agents/tests/runner/test_strategies.py -v`
Expected: FAIL

- [ ] **Step 3: Implement strategies**

Create `packages/agents/src/runner/strategies.py`:

```python
"""Built-in team strategy definitions for Arena tournaments."""
from __future__ import annotations

import logging

from packages.shared.src.types.models import TeamStrategy

logger = logging.getLogger(__name__)


BUILT_IN_STRATEGIES: dict[str, dict] = {
    "architecture-first": {
        "approach": "architecture_first",
        "model": "claude-opus-4-6",
        "priorities": ["architecture", "features", "tests", "docs"],
        "extra_rules": [
            "Write ARCHITECTURE.md BEFORE any code",
            "Create ADRs for every non-trivial design choice",
            "Design data models and API contracts before implementing",
            "Implement features one at a time, testing each before moving on",
        ],
    },
    "tdd-first": {
        "approach": "tdd_first",
        "model": "claude-sonnet-4-6",
        "priorities": ["tests", "features", "architecture", "docs"],
        "extra_rules": [
            "Write failing tests BEFORE writing any implementation",
            "Every function must have a test before it exists",
            "Run pytest after every file change",
            "Target 90%+ test coverage",
        ],
    },
    "speed-run": {
        "approach": "speed_run",
        "model": "claude-sonnet-4-6",
        "priorities": ["features", "tests", "architecture", "docs"],
        "extra_rules": [
            "Ship working features as fast as possible",
            "Implement the simplest solution that works",
            "Add tests after core features are working",
            "Skip ARCHITECTURE.md until the end",
        ],
    },
    "balanced": {
        "approach": "balanced",
        "model": "claude-sonnet-4-6",
        "priorities": ["architecture", "features", "tests", "docs"],
        "extra_rules": [
            "Start with a brief architecture sketch, then build iteratively",
            "Write tests alongside implementation",
            "Refactor as needed but don't over-engineer",
        ],
    },
}


def get_strategy(strategy_name: str, team_name: str) -> TeamStrategy:
    """Get a TeamStrategy by name, falling back to balanced if not found."""
    template = BUILT_IN_STRATEGIES.get(strategy_name)
    if template is None:
        logger.warning("Unknown strategy '%s', falling back to 'balanced'", strategy_name)
        template = BUILT_IN_STRATEGIES["balanced"]

    return TeamStrategy(name=team_name, **template)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yashbishnoi/Downloads/agentforge-arena && python -m pytest packages/agents/tests/runner/test_strategies.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
git add packages/agents/src/runner/strategies.py packages/agents/tests/runner/test_strategies.py
git commit -m "feat(agents): add built-in team strategy definitions

Four strategies: architecture-first (Opus), tdd-first, speed-run,
balanced (all Sonnet). Each shapes priorities and rules."
```

---

### Task 4: Create Prompt Builder

**Files:**
- Create: `packages/agents/src/runner/prompt.py`
- Test: `packages/agents/tests/runner/test_prompt.py`

- [ ] **Step 1: Write tests**

Create `packages/agents/tests/runner/test_prompt.py`:

```python
"""Tests for the initial prompt builder."""
from __future__ import annotations

import pytest
from packages.agents.src.runner.prompt import build_initial_prompt
from packages.agents.src.runner.strategies import get_strategy


def test_prompt_contains_challenge():
    """Challenge brief appears in the prompt."""
    strategy = get_strategy("balanced", "TestTeam")
    prompt = build_initial_prompt(
        challenge_brief="# Build a URL shortener\nCreate a REST API...",
        strategy=strategy,
        build_time_minutes=30,
    )
    assert "URL shortener" in prompt
    assert "REST API" in prompt


def test_prompt_contains_strategy_rules():
    """Strategy-specific rules appear in the prompt."""
    strategy = get_strategy("tdd-first", "TDD-Team")
    prompt = build_initial_prompt(
        challenge_brief="# Challenge",
        strategy=strategy,
        build_time_minutes=30,
    )
    assert "failing tests BEFORE" in prompt


def test_prompt_contains_time_limit():
    """Time limit appears in the prompt."""
    strategy = get_strategy("balanced", "T")
    prompt = build_initial_prompt(
        challenge_brief="# C",
        strategy=strategy,
        build_time_minutes=45,
    )
    assert "45 minutes" in prompt


def test_prompt_contains_self_config_instructions():
    """Prompt tells the agent to create CLAUDE.md and rules."""
    strategy = get_strategy("balanced", "T")
    prompt = build_initial_prompt(
        challenge_brief="# C",
        strategy=strategy,
        build_time_minutes=30,
    )
    assert "CLAUDE.md" in prompt
    assert ".claude/rules/" in prompt
    assert "RALPH" in prompt or "tests" in prompt.lower()


def test_prompt_contains_runnable_instructions():
    """Prompt tells the agent to make the app runnable."""
    strategy = get_strategy("balanced", "T")
    prompt = build_initial_prompt(
        challenge_brief="# C",
        strategy=strategy,
        build_time_minutes=30,
    )
    assert "uvicorn" in prompt or "pytest" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yashbishnoi/Downloads/agentforge-arena && python -m pytest packages/agents/tests/runner/test_prompt.py -v`
Expected: FAIL

- [ ] **Step 3: Implement prompt builder**

Create `packages/agents/src/runner/prompt.py`:

```python
"""Build the initial prompt for a Claude Code CLI session."""
from __future__ import annotations

from packages.shared.src.types.models import TeamStrategy


def build_initial_prompt(
    challenge_brief: str,
    strategy: TeamStrategy,
    build_time_minutes: int,
) -> str:
    """Build the complete initial prompt for a Claude Code CLI session.

    Combines the challenge brief, strategy-specific rules, self-configuration
    instructions, and RALPH loop guidance into a single prompt.
    """
    rules_block = "\n".join(f"- {r}" for r in strategy.extra_rules)
    priorities_block = "\n".join(
        f"  {i+1}. {p.title()}" for i, p in enumerate(strategy.priorities)
    )

    return f"""You are an autonomous AI agent competing in AgentForge Arena.
You have {build_time_minutes} minutes to build a complete, working application.

## Challenge
{challenge_brief}

## Your Strategy: {strategy.approach.replace('_', ' ').title()}
Priority order:
{priorities_block}

Strategy rules:
{rules_block}

## Self-Configuration (do this FIRST, spend max 2 minutes)
1. Create `CLAUDE.md` at the project root — include: what you're building, tech stack, key files, build/run commands
2. Create `.claude/rules/project-rules.md` — coding standards for your chosen stack
3. Create `.claude/hooks/post-write.sh` — auto-format hook (ruff format for .py, prettier for .ts/.tsx)

## Build Instructions
1. Read the challenge carefully and plan your approach
2. Create the project structure: `pyproject.toml`, `src/`, `tests/`, `Dockerfile`
3. Implement all features specified in the challenge
4. Write tests for every feature (target 80%+ coverage)
5. Ensure the application starts: `uvicorn src.main:app --host 0.0.0.0 --port 8000`
6. Create `ARCHITECTURE.md` documenting your design decisions
7. Create `README.md` with setup and run instructions

## RALPH Loop (Run-Analyze-Learn-Patch-Heal)
After implementing each major feature:
1. **Run**: `cd /workspace && pytest tests/ -v`
2. **Analyze**: Read the test output carefully
3. **Learn**: Identify what failed and why
4. **Patch**: Fix the failing code
5. **Heal**: Run tests again to confirm the fix
Do NOT move to the next feature until all current tests pass.

## Final Checklist (verify before you stop)
- [ ] `pip install -e .` succeeds
- [ ] `pytest tests/ -v` — all tests pass
- [ ] `ruff check src/` — zero errors
- [ ] `uvicorn src.main:app --port 8000` — server starts and /health returns 200
- [ ] CLAUDE.md, ARCHITECTURE.md, README.md all exist
- [ ] Dockerfile builds successfully

## Constraints
- All code in `src/`, all tests in `tests/`
- Python 3.12, use type hints everywhere
- Pydantic v2 for all data models
- No hardcoded secrets — use environment variables
- Time limit: {build_time_minutes} minutes total — manage your time wisely
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yashbishnoi/Downloads/agentforge-arena && python -m pytest packages/agents/tests/runner/test_prompt.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
git add packages/agents/src/runner/prompt.py packages/agents/tests/runner/test_prompt.py
git commit -m "feat(agents): add initial prompt builder for Claude Code CLI

Combines challenge brief, strategy rules, self-config instructions,
RALPH loop guidance, and final checklist into one autonomous prompt."
```

---

### Task 5: Create ClaudeCodeRunner

**Files:**
- Create: `packages/agents/src/runner/claude_code.py`
- Test: `packages/agents/tests/runner/test_claude_code.py`

This is the core new module. It spawns an actual `claude` CLI process and streams its output.

- [ ] **Step 1: Write tests**

Create `packages/agents/tests/runner/test_claude_code.py`:

```python
"""Tests for ClaudeCodeRunner."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from packages.agents.src.runner.claude_code import ClaudeCodeRunner
from packages.agents.src.runner.strategies import get_strategy


@pytest.fixture
def strategy():
    return get_strategy("balanced", "test-team")


@pytest.fixture
def runner(strategy, tmp_path):
    return ClaudeCodeRunner(
        team_id="team-001",
        workspace_path=str(tmp_path),
        strategy=strategy,
        event_callback=AsyncMock(),
    )


def test_runner_builds_command(runner):
    """Runner constructs the correct claude CLI command."""
    cmd = runner._build_command("Build a chat app")
    assert "claude" in cmd[0] or "claude" in " ".join(cmd)
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--dangerously-skip-permissions" in cmd


def test_runner_initial_state(runner):
    """Runner starts in non-running state."""
    status = runner.get_status()
    assert status.is_running is False
    assert status.team_id == "team-001"


@pytest.mark.asyncio
async def test_runner_stop_when_not_started(runner):
    """Stopping a runner that hasn't started is a no-op."""
    await runner.stop()  # Should not raise


@pytest.mark.asyncio
async def test_runner_start_spawns_process(runner, tmp_path):
    """Start creates a subprocess (mocked)."""
    # Write a fake challenge file
    challenge = tmp_path / "CHALLENGE.md"
    challenge.write_text("# Test Challenge\nBuild something.")

    mock_proc = AsyncMock()
    mock_proc.stdout = AsyncMock()
    mock_proc.stdout.__aiter__ = MagicMock(return_value=iter([]))
    mock_proc.pid = 12345
    mock_proc.returncode = None
    mock_proc.wait = AsyncMock(return_value=0)

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        await runner.start(str(challenge))
        assert runner._process is not None
        await runner.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yashbishnoi/Downloads/agentforge-arena && python -m pytest packages/agents/tests/runner/test_claude_code.py -v`
Expected: FAIL

- [ ] **Step 3: Implement ClaudeCodeRunner**

Create `packages/agents/src/runner/claude_code.py`:

```python
"""ClaudeCodeRunner — spawns and manages a Claude Code CLI session.

Each team in a tournament gets one ClaudeCodeRunner instance. The runner:
1. Spawns `claude` CLI with the challenge as the initial prompt
2. Streams stdout (stream-json format) and parses events
3. Forwards events to a callback (for spectator streaming)
4. Tracks aggregate stats (tokens, files, commands)
5. Handles graceful shutdown on phase timeout
"""
from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Callable, Coroutine
from datetime import datetime
from pathlib import Path
from typing import Any

from packages.agents.src.runner.prompt import build_initial_prompt
from packages.agents.src.runner.stream_parser import StreamParser
from packages.shared.src.types.models import RunnerEvent, RunnerStatus, TeamStrategy

logger = logging.getLogger(__name__)

# Type alias for the event callback
EventCallback = Callable[[str, RunnerEvent], Coroutine[Any, Any, None]]


class ClaudeCodeRunner:
    """Runs an actual Claude Code CLI session inside a team's workspace."""

    def __init__(
        self,
        team_id: str,
        workspace_path: str,
        strategy: TeamStrategy,
        event_callback: EventCallback | None = None,
        model: str | None = None,
    ) -> None:
        self.team_id = team_id
        self.workspace_path = workspace_path
        self.strategy = strategy
        self._callback = event_callback
        self._model = model or strategy.model
        self._process: asyncio.subprocess.Process | None = None
        self._stream_task: asyncio.Task | None = None
        self._parser = StreamParser()
        self._started_at: datetime | None = None
        self._exit_code: int | None = None

    def _build_command(self, prompt: str) -> list[str]:
        """Build the claude CLI command with all flags."""
        return [
            "claude",
            "--output-format", "stream-json",
            "--model", self._model,
            "--dangerously-skip-permissions",
            "--verbose",
            "-p", prompt,
        ]

    async def start(self, challenge_path: str) -> None:
        """Start the Claude Code CLI with the challenge as initial prompt.

        Args:
            challenge_path: Path to CHALLENGE.md file.
        """
        # Read challenge brief
        challenge_brief = Path(challenge_path).read_text(encoding="utf-8")

        # Build the initial prompt
        prompt = build_initial_prompt(
            challenge_brief=challenge_brief,
            strategy=self.strategy,
            build_time_minutes=30,  # Default, overridden by orchestrator
        )

        cmd = self._build_command(prompt)
        logger.info("Starting Claude Code CLI for team %s: %s", self.team_id, " ".join(cmd[:5]))

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.workspace_path,
        )

        self._started_at = datetime.utcnow()
        logger.info("Claude Code CLI started for team %s (PID: %s)", self.team_id, self._process.pid)

        # Start streaming stdout in background
        self._stream_task = asyncio.create_task(self._stream_output())

    async def _stream_output(self) -> None:
        """Read stdout line by line, parse events, and forward to callback."""
        if self._process is None or self._process.stdout is None:
            return

        try:
            async for line_bytes in self._process.stdout:
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                event = self._parser.feed(line)
                if event and self._callback:
                    try:
                        await self._callback(self.team_id, event)
                    except Exception:
                        logger.exception("Event callback failed for team %s", self.team_id)

        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Stream reading failed for team %s", self.team_id)
        finally:
            # Wait for process to finish
            if self._process and self._process.returncode is None:
                try:
                    self._exit_code = await asyncio.wait_for(self._process.wait(), timeout=10)
                except asyncio.TimeoutError:
                    self._process.kill()
                    self._exit_code = -9
            elif self._process:
                self._exit_code = self._process.returncode

            logger.info(
                "Claude Code CLI finished for team %s (exit=%s, files=%d, cmds=%d)",
                self.team_id,
                self._exit_code,
                self._parser.files_written,
                self._parser.commands_run,
            )

    async def stop(self) -> None:
        """Gracefully stop the Claude Code CLI process."""
        if self._process is None:
            return

        if self._process.returncode is not None:
            # Already finished
            self._exit_code = self._process.returncode
            return

        # Send SIGTERM first
        try:
            self._process.send_signal(signal.SIGTERM)
            try:
                self._exit_code = await asyncio.wait_for(self._process.wait(), timeout=10)
            except asyncio.TimeoutError:
                # Force kill after 10s
                logger.warning("Force killing Claude Code CLI for team %s", self.team_id)
                self._process.kill()
                self._exit_code = await self._process.wait()
        except ProcessLookupError:
            pass

        # Cancel stream task
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass

    def get_status(self) -> RunnerStatus:
        """Get current status of the CLI process."""
        is_running = (
            self._process is not None
            and self._process.returncode is None
        )
        return RunnerStatus(
            team_id=self.team_id,
            is_running=is_running,
            pid=self._process.pid if self._process else None,
            exit_code=self._exit_code,
            total_tokens=0,  # TODO: parse from Claude Code output when available
            files_written=self._parser.files_written,
            commands_run=self._parser.commands_run,
            started_at=self._started_at,
            last_event_at=(
                self._parser.events[-1].timestamp
                if self._parser.events
                else None
            ),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yashbishnoi/Downloads/agentforge-arena && python -m pytest packages/agents/tests/runner/test_claude_code.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
git add packages/agents/src/runner/claude_code.py packages/agents/tests/runner/test_claude_code.py
git commit -m "feat(agents): add ClaudeCodeRunner — spawns real Claude Code CLI

Core module that replaces the AgentProcess LLM wrapper. Spawns an actual
claude CLI process, streams stdout events, handles graceful shutdown."
```

---

### Task 6: Create RunnerManager

**Files:**
- Create: `packages/agents/src/runner/manager.py`
- Test: `packages/agents/tests/runner/test_manager.py`

- [ ] **Step 1: Write tests**

Create `packages/agents/tests/runner/test_manager.py`:

```python
"""Tests for RunnerManager."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from packages.agents.src.runner.manager import RunnerManager
from packages.agents.src.runner.strategies import get_strategy
from packages.shared.src.types.models import TeamStrategy


@pytest.fixture
def manager():
    event_bus = AsyncMock()
    return RunnerManager(event_bus=event_bus)


def test_manager_starts_empty(manager):
    """Manager starts with no runners."""
    assert manager.active_runners == {}


@pytest.mark.asyncio
async def test_start_team_creates_runner(manager, tmp_path):
    """start_team creates a ClaudeCodeRunner and tracks it."""
    team_id = uuid4()
    strategy = get_strategy("balanced", "test")
    challenge_path = tmp_path / "CHALLENGE.md"
    challenge_path.write_text("# Test Challenge")

    with patch("packages.agents.src.runner.manager.ClaudeCodeRunner") as MockRunner:
        mock_instance = AsyncMock()
        mock_instance.get_status.return_value = AsyncMock(is_running=True)
        MockRunner.return_value = mock_instance

        await manager.start_team(
            team_id=team_id,
            workspace_path=str(tmp_path),
            strategy=strategy,
            challenge_path=str(challenge_path),
            build_time_minutes=30,
        )

        assert team_id in manager.active_runners
        mock_instance.start.assert_called_once()


@pytest.mark.asyncio
async def test_stop_team(manager, tmp_path):
    """stop_team stops the runner and removes it."""
    team_id = uuid4()
    strategy = get_strategy("balanced", "test")
    challenge_path = tmp_path / "CHALLENGE.md"
    challenge_path.write_text("# Test")

    with patch("packages.agents.src.runner.manager.ClaudeCodeRunner") as MockRunner:
        mock_instance = AsyncMock()
        MockRunner.return_value = mock_instance

        await manager.start_team(team_id, str(tmp_path), strategy, str(challenge_path), 30)
        await manager.stop_team(team_id)

        mock_instance.stop.assert_called_once()
        assert team_id not in manager.active_runners


@pytest.mark.asyncio
async def test_stop_all(manager, tmp_path):
    """stop_all stops every active runner."""
    challenge_path = tmp_path / "CHALLENGE.md"
    challenge_path.write_text("# Test")

    with patch("packages.agents.src.runner.manager.ClaudeCodeRunner") as MockRunner:
        mock_instance = AsyncMock()
        MockRunner.return_value = mock_instance

        t1, t2 = uuid4(), uuid4()
        s = get_strategy("balanced", "t")
        await manager.start_team(t1, str(tmp_path), s, str(challenge_path), 30)
        await manager.start_team(t2, str(tmp_path), s, str(challenge_path), 30)

        assert len(manager.active_runners) == 2
        await manager.stop_all()
        assert len(manager.active_runners) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yashbishnoi/Downloads/agentforge-arena && python -m pytest packages/agents/tests/runner/test_manager.py -v`
Expected: FAIL

- [ ] **Step 3: Implement RunnerManager**

Create `packages/agents/src/runner/manager.py`:

```python
"""RunnerManager — manages ClaudeCodeRunner instances across teams."""
from __future__ import annotations

import logging
from uuid import UUID

from packages.agents.src.runner.claude_code import ClaudeCodeRunner
from packages.shared.src.events.bus import EventBus
from packages.shared.src.types.models import RunnerEvent, RunnerStatus, TeamStrategy

logger = logging.getLogger(__name__)


class RunnerManager:
    """Manages multiple ClaudeCodeRunner instances for tournament teams."""

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus
        self.active_runners: dict[UUID, ClaudeCodeRunner] = {}

    async def _event_callback(self, team_id: str, event: RunnerEvent) -> None:
        """Forward runner events to the event bus for spectators."""
        event_type_map = {
            "tool_use": "agent.tool.use",
            "tool_result": "agent.tool.result",
            "assistant": "agent.thinking",
        }
        bus_event_type = event_type_map.get(event.event_type, f"agent.{event.event_type}")

        await self._events.publish(
            bus_event_type,
            source=f"runner.{team_id}",
            payload={
                "team_id": team_id,
                "tool_name": event.tool_name,
                "content_preview": (event.content or "")[:500],
            },
        )

    async def start_team(
        self,
        team_id: UUID,
        workspace_path: str,
        strategy: TeamStrategy,
        challenge_path: str,
        build_time_minutes: int,
    ) -> None:
        """Start a Claude Code CLI session for a team."""
        runner = ClaudeCodeRunner(
            team_id=str(team_id),
            workspace_path=workspace_path,
            strategy=strategy,
            event_callback=self._event_callback,
        )

        await runner.start(challenge_path)
        self.active_runners[team_id] = runner

        logger.info("Started runner for team %s (strategy=%s)", team_id, strategy.approach)

    async def stop_team(self, team_id: UUID) -> None:
        """Stop a team's Claude Code CLI session."""
        runner = self.active_runners.pop(team_id, None)
        if runner:
            await runner.stop()
            logger.info("Stopped runner for team %s", team_id)

    async def get_team_status(self, team_id: UUID) -> RunnerStatus | None:
        """Get status of a team's runner."""
        runner = self.active_runners.get(team_id)
        if runner:
            return runner.get_status()
        return None

    async def stop_all(self) -> None:
        """Stop all active runners. Used in shutdown."""
        team_ids = list(self.active_runners.keys())
        for team_id in team_ids:
            await self.stop_team(team_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yashbishnoi/Downloads/agentforge-arena && python -m pytest packages/agents/tests/runner/test_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
git add packages/agents/src/runner/manager.py packages/agents/tests/runner/test_manager.py
git commit -m "feat(agents): add RunnerManager for multi-team CLI orchestration

Manages ClaudeCodeRunner instances per team, forwards events to
Redis event bus for spectator streaming."
```

---

### Task 7: Create First Real Challenge (Realtime Chat)

**Files:**
- Create: `challenges/library/realtime-chat/CHALLENGE.md`
- Create: `challenges/library/realtime-chat/hidden_tests/conftest.py`
- Create: `challenges/library/realtime-chat/hidden_tests/test_api.py`
- Create: `challenges/library/realtime-chat/hidden_tests/test_websocket.py`
- Create: `challenges/library/realtime-chat/metadata.json`
- Create: `challenges/library/realtime-chat/scoring_config.json`

- [ ] **Step 1: Create challenge directory structure**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
mkdir -p challenges/library/realtime-chat/hidden_tests
```

- [ ] **Step 2: Write CHALLENGE.md**

Create `challenges/library/realtime-chat/CHALLENGE.md`:

```markdown
# Challenge: Real-Time Chat Application

## Overview
Build a real-time chat application with WebSocket support, room management,
message persistence, and online presence tracking.

## Requirements

### Core Features
1. **Room Management** — Create, list, and get rooms via REST API
2. **Message Persistence** — Send messages to rooms, retrieve message history with pagination
3. **WebSocket Real-Time** — Users connect via WebSocket, join rooms, send messages, and receive broadcasts
4. **Online Presence** — Track who is currently in each room, broadcast join/leave events
5. **Message Search** — Search messages by keyword within a room

### API Endpoints (REST)
- `POST /rooms` — Create a room (body: `{"name": "room-name"}`)
- `GET /rooms` — List all rooms
- `GET /rooms/{id}` — Get room details
- `POST /rooms/{id}/messages` — Send a message (body: `{"username": "...", "content": "..."}`)
- `GET /rooms/{id}/messages?limit=50&offset=0` — Get paginated messages (newest first)
- `GET /rooms/{id}/messages/search?keyword=...` — Search messages
- `GET /health` — Health check (returns `{"status": "healthy"}`)

### WebSocket Protocol
- Connect: `ws://localhost:8000/ws`
- Join room: `{"type": "join", "room_id": 1, "username": "alice"}`
- Send message: `{"type": "message", "room_id": 1, "content": "Hello!"}`
- Typing indicator: `{"type": "typing", "room_id": 1, "username": "alice"}`
- Leave room: `{"type": "leave", "room_id": 1, "username": "alice"}`

### Technical Requirements
- Python 3.12 + FastAPI
- SQLite (aiosqlite) for message persistence
- Pydantic v2 for all request/response models
- WebSocket manager for connection tracking
- Async everywhere — no blocking I/O

### Hidden Test Hints
- Tests will create rooms, send messages, and verify retrieval
- Tests will connect via WebSocket, join rooms, and verify message broadcasts
- Tests will check pagination (limit/offset) correctness
- Tests will verify presence tracking (join/leave broadcasts)
- Tests will check error handling (nonexistent rooms, invalid messages)

## Time Limit
30 minutes

## Scoring Focus
- Functionality (30%): Do the REST endpoints and WebSocket work correctly?
- Code Quality (20%): Clean code, proper typing, no lint errors
- Test Coverage (15%): How well did you test your own code?
- Architecture (10%): Separation of concerns, clear module structure
- Innovation (10%): Any extra features beyond requirements?
```

- [ ] **Step 3: Write hidden test conftest**

Create `challenges/library/realtime-chat/hidden_tests/conftest.py`:

```python
"""Hidden test fixtures for the real-time chat challenge."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    """HTTP client pointed at the team's running server."""
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=10.0) as c:
        yield c
```

- [ ] **Step 4: Write hidden API tests**

Create `challenges/library/realtime-chat/hidden_tests/test_api.py`:

```python
"""Hidden tests: REST API functionality."""
from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_health_endpoint(client: httpx.AsyncClient):
    """Health endpoint returns 200."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "healthy"


@pytest.mark.asyncio
async def test_create_room(client: httpx.AsyncClient):
    """Create a room and get it back."""
    resp = await client.post("/rooms", json={"name": "hidden-test-room"})
    assert resp.status_code in (200, 201)
    room = resp.json()
    assert room["name"] == "hidden-test-room"
    assert "id" in room


@pytest.mark.asyncio
async def test_list_rooms(client: httpx.AsyncClient):
    """List rooms returns at least the created room."""
    await client.post("/rooms", json={"name": "list-test-room"})
    resp = await client.get("/rooms")
    assert resp.status_code == 200
    rooms = resp.json()
    assert isinstance(rooms, list)
    assert len(rooms) >= 1


@pytest.mark.asyncio
async def test_send_and_get_messages(client: httpx.AsyncClient):
    """Send a message and retrieve it."""
    room_resp = await client.post("/rooms", json={"name": "msg-test-room"})
    room_id = room_resp.json()["id"]

    msg_resp = await client.post(
        f"/rooms/{room_id}/messages",
        json={"username": "tester", "content": "Hello from hidden test"},
    )
    assert msg_resp.status_code in (200, 201)

    get_resp = await client.get(f"/rooms/{room_id}/messages")
    assert get_resp.status_code == 200
    data = get_resp.json()
    messages = data.get("messages", data) if isinstance(data, dict) else data
    assert any("Hello from hidden test" in str(m) for m in messages)


@pytest.mark.asyncio
async def test_pagination(client: httpx.AsyncClient):
    """Pagination returns correct page sizes."""
    room_resp = await client.post("/rooms", json={"name": "page-test-room"})
    room_id = room_resp.json()["id"]

    for i in range(10):
        await client.post(
            f"/rooms/{room_id}/messages",
            json={"username": "bot", "content": f"Message {i}"},
        )

    page1 = await client.get(f"/rooms/{room_id}/messages?limit=5&offset=0")
    assert page1.status_code == 200
    data1 = page1.json()
    msgs1 = data1.get("messages", data1) if isinstance(data1, dict) else data1
    assert len(msgs1) == 5


@pytest.mark.asyncio
async def test_search_messages(client: httpx.AsyncClient):
    """Search finds matching messages."""
    room_resp = await client.post("/rooms", json={"name": "search-test-room"})
    room_id = room_resp.json()["id"]

    await client.post(f"/rooms/{room_id}/messages", json={"username": "a", "content": "Python is great"})
    await client.post(f"/rooms/{room_id}/messages", json={"username": "b", "content": "I love JavaScript"})
    await client.post(f"/rooms/{room_id}/messages", json={"username": "c", "content": "Python rocks"})

    search_resp = await client.get(f"/rooms/{room_id}/messages/search?keyword=Python")
    assert search_resp.status_code == 200
    results = search_resp.json()
    if isinstance(results, dict):
        results = results.get("messages", results.get("results", []))
    assert len(results) == 2


@pytest.mark.asyncio
async def test_nonexistent_room_returns_404(client: httpx.AsyncClient):
    """Accessing a nonexistent room returns 404."""
    resp = await client.get("/rooms/99999")
    assert resp.status_code == 404
```

- [ ] **Step 5: Write hidden WebSocket tests**

Create `challenges/library/realtime-chat/hidden_tests/test_websocket.py`:

```python
"""Hidden tests: WebSocket functionality."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import websockets


@pytest.mark.asyncio
async def test_websocket_connect():
    """Can connect to WebSocket endpoint."""
    try:
        async with websockets.connect("ws://localhost:8000/ws", open_timeout=5) as ws:
            assert ws.open
    except Exception as e:
        pytest.fail(f"WebSocket connection failed: {e}")


@pytest.mark.asyncio
async def test_websocket_join_room(client: httpx.AsyncClient):
    """Join a room via WebSocket and receive confirmation."""
    room_resp = await client.post("/rooms", json={"name": "ws-join-room"})
    room_id = room_resp.json()["id"]

    async with websockets.connect("ws://localhost:8000/ws", open_timeout=5) as ws:
        await ws.send(json.dumps({"type": "join", "room_id": room_id, "username": "ws-tester"}))
        response = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(response)
        # Accept various confirmation formats
        assert data.get("type") in ("join_ack", "joined", "system", "presence", "user_joined")


@pytest.mark.asyncio
async def test_websocket_message_broadcast(client: httpx.AsyncClient):
    """Messages sent via WebSocket are broadcast to other room members."""
    room_resp = await client.post("/rooms", json={"name": "ws-broadcast-room"})
    room_id = room_resp.json()["id"]

    async with websockets.connect("ws://localhost:8000/ws", open_timeout=5) as ws1:
        async with websockets.connect("ws://localhost:8000/ws", open_timeout=5) as ws2:
            # Both join the room
            await ws1.send(json.dumps({"type": "join", "room_id": room_id, "username": "alice"}))
            await ws2.send(json.dumps({"type": "join", "room_id": room_id, "username": "bob"}))

            # Drain join confirmations
            await asyncio.wait_for(ws1.recv(), timeout=5)
            await asyncio.wait_for(ws2.recv(), timeout=5)
            # Drain possible join broadcast to other user
            try:
                await asyncio.wait_for(ws1.recv(), timeout=1)
            except asyncio.TimeoutError:
                pass
            try:
                await asyncio.wait_for(ws2.recv(), timeout=1)
            except asyncio.TimeoutError:
                pass

            # Alice sends a message
            await ws1.send(json.dumps({
                "type": "message",
                "room_id": room_id,
                "content": "Hello from Alice!",
            }))

            # Bob should receive the broadcast
            msg = await asyncio.wait_for(ws2.recv(), timeout=5)
            data = json.loads(msg)
            assert "Alice" in str(data) or "Hello from Alice" in str(data)
```

- [ ] **Step 6: Write metadata and scoring config**

Create `challenges/library/realtime-chat/metadata.json`:

```json
{
  "id": "realtime-chat",
  "title": "Real-Time Chat Application",
  "category": "real_time",
  "difficulty": "medium",
  "time_limit_minutes": 30,
  "tags": ["websocket", "fastapi", "sqlite", "real-time", "chat"],
  "requirements_count": 5,
  "hidden_test_count": 9,
  "created_at": "2026-04-02"
}
```

Create `challenges/library/realtime-chat/scoring_config.json`:

```json
{
  "scoring_weights": {
    "functionality": 0.30,
    "code_quality": 0.20,
    "test_coverage": 0.15,
    "ux_design": 0.10,
    "architecture": 0.15,
    "innovation": 0.10
  },
  "notes": "Architecture weight increased because WebSocket design quality matters for real-time apps. UX weight decreased since this is primarily a backend challenge."
}
```

- [ ] **Step 7: Commit**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
git add challenges/
git commit -m "feat(challenges): add realtime-chat challenge with hidden test suite

9 hidden tests covering REST API, WebSocket, pagination, search,
and error handling. Includes scoring config with architecture-weighted scoring."
```

---

### Task 8: Update Orchestrator to Use RunnerManager

**Files:**
- Modify: `packages/core/src/tournament/orchestrator.py`
- Test: `packages/core/tests/test_orchestrator_v2.py`

- [ ] **Step 1: Write tests for the updated orchestrator**

Create `packages/core/tests/test_orchestrator_v2.py`:

```python
"""Tests for the updated orchestrator using RunnerManager."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from packages.core.src.tournament.orchestrator import (
    TournamentOrchestrator,
    PHASE_TRANSITIONS,
)
from packages.shared.src.types.models import (
    TeamStrategy,
    Tournament,
    TournamentConfig,
    TournamentFormat,
    TournamentPhase,
)


@pytest.fixture
def mock_services():
    return {
        "event_bus": AsyncMock(),
        "sandbox_manager": AsyncMock(),
        "runner_manager": AsyncMock(),
        "judge_service": AsyncMock(),
    }


@pytest.fixture
def orchestrator(mock_services):
    return TournamentOrchestrator(**mock_services)


def test_simplified_phase_transitions():
    """Phase transitions follow: PREP → BUILD → CROSS_REVIEW → FIX → JUDGE → COMPLETE."""
    assert PHASE_TRANSITIONS[TournamentPhase.PREP] == TournamentPhase.BUILD
    assert PHASE_TRANSITIONS[TournamentPhase.BUILD] == TournamentPhase.CROSS_REVIEW
    assert PHASE_TRANSITIONS[TournamentPhase.CROSS_REVIEW] == TournamentPhase.FIX
    assert PHASE_TRANSITIONS[TournamentPhase.FIX] == TournamentPhase.JUDGE
    assert PHASE_TRANSITIONS[TournamentPhase.JUDGE] == TournamentPhase.COMPLETE


@pytest.mark.asyncio
async def test_create_tournament(orchestrator, mock_services):
    """create_tournament validates and stores tournament."""
    config = TournamentConfig(
        format=TournamentFormat.DUEL,
        teams=[
            TeamStrategy(name="Alpha", approach="architecture_first"),
            TeamStrategy(name="Bravo", approach="tdd_first"),
        ],
        build_time_minutes=30,
    )

    with patch.object(orchestrator, "_select_random_challenge", return_value="realtime-chat"):
        with patch("packages.core.src.tournament.orchestrator.get_session"):
            tournament = await orchestrator.create_tournament(config)

    assert tournament.current_phase == TournamentPhase.PREP
    assert tournament.id in orchestrator._active_tournaments
    mock_services["event_bus"].publish.assert_called()


@pytest.mark.asyncio
async def test_start_tournament_creates_sandboxes_and_runners(orchestrator, mock_services):
    """start_tournament provisions sandboxes and starts ClaudeCodeRunners."""
    config = TournamentConfig(
        format=TournamentFormat.DUEL,
        teams=[
            TeamStrategy(name="Alpha", approach="architecture_first"),
            TeamStrategy(name="Bravo", approach="tdd_first"),
        ],
    )

    mock_services["sandbox_manager"].create_sandbox.return_value = "sandbox-123"

    with patch.object(orchestrator, "_select_random_challenge", return_value="realtime-chat"):
        with patch.object(orchestrator, "_load_challenge", return_value="# Challenge"):
            with patch("packages.core.src.tournament.orchestrator.get_session"):
                tournament = await orchestrator.create_tournament(config)
                await orchestrator.start_tournament(tournament.id)

    # Should have created 2 sandboxes
    assert mock_services["sandbox_manager"].create_sandbox.call_count == 2

    # Should have started 2 runners
    assert mock_services["runner_manager"].start_team.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yashbishnoi/Downloads/agentforge-arena && python -m pytest packages/core/tests/test_orchestrator_v2.py -v`
Expected: FAIL — orchestrator still uses old agent_manager

- [ ] **Step 3: Update the orchestrator**

Modify `packages/core/src/tournament/orchestrator.py`. The key changes:

**Replace imports** (line 21-27): Remove `TeamDB` import (handle separately), keep the rest.

**Simplify PHASE_TRANSITIONS** (line 73-81): Remove RESEARCH and ARCHITECTURE phases:

```python
PHASE_TRANSITIONS: dict[TournamentPhase, TournamentPhase] = {
    TournamentPhase.PREP: TournamentPhase.BUILD,
    TournamentPhase.BUILD: TournamentPhase.CROSS_REVIEW,
    TournamentPhase.CROSS_REVIEW: TournamentPhase.FIX,
    TournamentPhase.FIX: TournamentPhase.JUDGE,
    TournamentPhase.JUDGE: TournamentPhase.COMPLETE,
}
```

**Simplify DEFAULT_PHASE_TIMINGS** (line 33-70): Use `build_time_minutes` from config instead of per-phase timings. Keep as fallback but merge research+architecture+build:

```python
DEFAULT_PHASE_TIMINGS: dict[TournamentFormat, dict[TournamentPhase, int]] = {
    TournamentFormat.DUEL: {
        TournamentPhase.PREP: 120,            # 2 min
        TournamentPhase.BUILD: 1800,          # 30 min (configurable via build_time_minutes)
        TournamentPhase.CROSS_REVIEW: 600,    # 10 min
        TournamentPhase.FIX: 600,             # 10 min
        TournamentPhase.JUDGE: 300,           # 5 min
    },
    TournamentFormat.STANDARD: {
        TournamentPhase.PREP: 120,
        TournamentPhase.BUILD: 3600,          # 60 min
        TournamentPhase.CROSS_REVIEW: 600,
        TournamentPhase.FIX: 600,
        TournamentPhase.JUDGE: 600,
    },
    TournamentFormat.LEAGUE: {
        TournamentPhase.PREP: 120,
        TournamentPhase.BUILD: 2700,          # 45 min
        TournamentPhase.CROSS_REVIEW: 600,
        TournamentPhase.FIX: 600,
        TournamentPhase.JUDGE: 600,
    },
    TournamentFormat.GRAND_PRIX: {
        TournamentPhase.PREP: 120,
        TournamentPhase.BUILD: 1800,          # 30 min
        TournamentPhase.CROSS_REVIEW: 600,
        TournamentPhase.FIX: 600,
        TournamentPhase.JUDGE: 600,
    },
}
```

**Update `__init__`** (line 87-100): Replace `agent_manager` with `runner_manager`:

```python
def __init__(
    self,
    event_bus: EventBus,
    sandbox_manager: object,
    runner_manager: object,    # RunnerManager — replaces AgentTeamManager
    judge_service: object,
) -> None:
    self._events = event_bus
    self._sandbox = sandbox_manager
    self._runners = runner_manager
    self._judge = judge_service
    self._active_tournaments: dict[UUID, Tournament] = {}
    self._phase_timers: dict[UUID, asyncio.Task[None]] = {}
    self._health_tasks: dict[UUID, asyncio.Task[None]] = {}
```

**Update `start_tournament`** (line 162-237): Replace agent spawning with runner starting:

```python
async def start_tournament(self, tournament_id: UUID) -> Tournament:
    """Start a created tournament — provision sandboxes and start Claude Code CLIs."""
    tournament = self._active_tournaments.get(tournament_id)
    if not tournament:
        raise ValueError(f"Tournament {tournament_id} not found")

    if tournament.current_phase != TournamentPhase.PREP:
        raise ValueError(f"Tournament is in phase {tournament.current_phase}, expected PREP")

    tournament.started_at = datetime.utcnow()

    # Load challenge brief
    challenge_brief = await self._load_challenge(tournament.challenge_id)

    for i, team_strategy in enumerate(tournament.config.teams):
        team_id = uuid4()

        # 1. Create sandbox
        sandbox_id = await self._sandbox.create_sandbox(
            team_id=str(team_id),
            memory=team_strategy.sandbox_memory,
            cpus=team_strategy.sandbox_cpus,
        )

        # 2. Write challenge into sandbox
        settings = get_settings()
        workspace = f"{settings.sandbox.workspace_base}/team-{team_id}/project"
        challenge_path = f"{workspace}/CHALLENGE.md"
        await self._sandbox.write_file(
            team_id=str(team_id),
            path="CHALLENGE.md",
            content=challenge_brief,
        )

        # 3. Start Claude Code CLI runner
        await self._runners.start_team(
            team_id=team_id,
            workspace_path=workspace,
            strategy=team_strategy,
            challenge_path=challenge_path,
            build_time_minutes=tournament.config.build_time_minutes,
        )

        tournament.team_ids.append(team_id)

        await self._events.publish(
            "tournament.team.started",
            source="core.orchestrator",
            tournament_id=tournament_id,
            team_id=team_id,
            payload={
                "team_name": team_strategy.name,
                "sandbox_id": sandbox_id,
                "strategy": team_strategy.approach,
                "model": team_strategy.model,
            },
        )

    # Transition to BUILD phase
    await self._transition_phase(tournament, TournamentPhase.BUILD)

    # Start health monitoring
    self._health_tasks[tournament_id] = asyncio.create_task(
        self._health_monitor(tournament)
    )

    await self._events.publish(
        "tournament.started",
        source="core.orchestrator",
        tournament_id=tournament_id,
        payload={"team_ids": [str(t) for t in tournament.team_ids]},
    )

    return tournament
```

**Simplify `_execute_phase_setup`** (line 325-366): Remove research/architecture phase handlers:

```python
async def _execute_phase_setup(
    self, tournament: Tournament, phase: TournamentPhase
) -> None:
    """Execute phase-specific initialization logic."""
    match phase:
        case TournamentPhase.BUILD:
            # Claude Code CLIs are already running — just publish event
            for team_id in tournament.team_ids:
                await self._notify_team(
                    tournament.id, team_id, "build_start",
                    {"message": "BUILD phase started. Claude Code CLI is running autonomously."}
                )

        case TournamentPhase.CROSS_REVIEW:
            await self._setup_cross_review(tournament)

        case TournamentPhase.FIX:
            for team_id in tournament.team_ids:
                await self._notify_team(
                    tournament.id, team_id, "fix_start",
                    {"message": "Fix phase. Address cross-review feedback."}
                )

        case TournamentPhase.JUDGE:
            # Stop all CLIs before judging
            for team_id in tournament.team_ids:
                await self._runners.stop_team(team_id)
            await self._invoke_judging(tournament)

        case TournamentPhase.COMPLETE:
            await self._complete_tournament(tournament)
```

**Update `_health_monitor`** (line 442-471): Check runner status instead of agent health:

```python
async def _health_monitor(self, tournament: Tournament) -> None:
    """Monitor runner health every 30 seconds during active phases."""
    try:
        while tournament.current_phase not in (
            TournamentPhase.COMPLETE,
            TournamentPhase.CANCELLED,
        ):
            for team_id in tournament.team_ids:
                status = await self._runners.get_team_status(team_id)
                if status and not status.is_running and tournament.current_phase == TournamentPhase.BUILD:
                    logger.info("Team %s CLI finished (exit=%s)", team_id, status.exit_code)
                    await self._events.publish(
                        "tournament.team.finished",
                        source="core.orchestrator",
                        tournament_id=tournament.id,
                        team_id=team_id,
                        payload={
                            "exit_code": status.exit_code,
                            "files_written": status.files_written,
                            "commands_run": status.commands_run,
                        },
                    )

            await self._check_budget(tournament)
            await asyncio.sleep(30)
    except asyncio.CancelledError:
        pass
```

**Update `cancel_tournament`** (line 495-545): Replace agent teardown with runner stop:

Replace `await self._sandbox.destroy_sandbox(str(team_id))` section (line 513-517) to also stop runners:

```python
# Stop runners
await self._runners.stop_all()

# Teardown sandboxes
for team_id in tournament.team_ids:
    try:
        await self._sandbox.destroy_sandbox(str(team_id))
    except Exception:
        logger.warning("Failed to destroy sandbox for team %s", team_id)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/yashbishnoi/Downloads/agentforge-arena && python -m pytest packages/core/tests/test_orchestrator_v2.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
git add packages/core/src/tournament/orchestrator.py packages/core/tests/test_orchestrator_v2.py
git commit -m "refactor(core): orchestrator uses RunnerManager instead of AgentTeamManager

Simplified phases: PREP → BUILD → CROSS_REVIEW → FIX → JUDGE → COMPLETE.
Teams now run Claude Code CLI sessions instead of LLM-wrapper agents.
BUILD phase starts CLI, JUDGE phase stops CLI before scoring."
```

---

### Task 9: Update Sandbox Manager (Port Mapping + Env)

**Files:**
- Modify: `packages/sandbox/src/docker/manager.py`

- [ ] **Step 1: Add port mapping to `create_sandbox`**

Update `packages/sandbox/src/docker/manager.py`.

Add `port` field to `SandboxInfo` (line 21-30):

```python
@dataclass
class SandboxInfo:
    """Metadata about a running sandbox."""

    team_id: str
    sandbox_id: str
    workspace_path: str
    memory: str
    cpus: int
    host_port: int = 0
    status: str = "running"
    network_allows: list[str] = field(default_factory=list)
```

Update `create_sandbox` signature (line 39-46) to accept a `host_port` parameter:

```python
async def create_sandbox(
    self,
    team_id: str,
    *,
    memory: str = "4g",
    cpus: int = 2,
    host_port: int = 0,
) -> str:
```

Update the `SandboxInfo` creation (line 86-94) to include `host_port`:

```python
info = SandboxInfo(
    team_id=team_id,
    sandbox_id=sandbox_id,
    workspace_path=workspace,
    memory=memory,
    cpus=cpus,
    host_port=host_port,
    network_allows=network_allows,
)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
git add packages/sandbox/src/docker/manager.py
git commit -m "feat(sandbox): add host_port tracking to SandboxInfo

Enables mapping team app ports (8000 inside sandbox) to unique host ports
for live demos and judge health checks."
```

---

### Task 10: Update Judge to Copy Hidden Tests Into Workspace

**Files:**
- Modify: `packages/judge/src/scoring/service.py`

- [ ] **Step 1: Update `_judge_match` to copy hidden tests**

In `packages/judge/src/scoring/service.py`, update `_judge_match` (line 342-408).

After resolving `hidden_tests_dir` (line 357-364), add a step to copy hidden tests into the workspace so `pytest` can find the team's source code:

```python
async def _judge_match(
    self,
    tournament_id: UUID,
    team_a_id: UUID,
    team_b_id: UUID,
    challenge_id: str,
) -> MatchResult:
    """Judge a single match between two teams."""
    from packages.shared.src.config import get_settings
    settings = get_settings()

    workspace_a = f"{settings.sandbox.workspace_base}/team-{team_a_id}/project"
    workspace_b = f"{settings.sandbox.workspace_base}/team-{team_b_id}/project"

    # Resolve hidden tests from challenge library
    repo_root = Path(__file__).resolve().parents[4]
    hidden_tests_src = repo_root / "challenges" / "library" / challenge_id / "hidden_tests"

    # Copy hidden tests into each team's workspace for pytest to find their src/
    hidden_a = await self._inject_hidden_tests(workspace_a, hidden_tests_src)
    hidden_b = await self._inject_hidden_tests(workspace_b, hidden_tests_src)

    # Load scoring config overrides if available
    scoring_config_file = repo_root / "challenges" / "library" / challenge_id / "scoring_config.json"
    if scoring_config_file.is_file():
        try:
            config_data = json.loads(scoring_config_file.read_text())
            weight_overrides = config_data.get("scoring_weights", {})
            if weight_overrides:
                self._apply_scoring_overrides(weight_overrides)
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to load scoring config for %s", challenge_id)

    # Run all judges in parallel for both teams
    team_a_scores, team_b_scores = await asyncio.gather(
        self._score_team(workspace_a, hidden_a),
        self._score_team(workspace_b, hidden_b),
    )

    # Calculate totals
    total_a = sum(s.score * s.weight for s in team_a_scores)
    total_b = sum(s.score * s.weight for s in team_b_scores)

    # Determine winner
    winner = None
    is_draw = False
    if abs(total_a - total_b) < 1.0:
        is_draw = True
    elif total_a > total_b:
        winner = team_a_id
    else:
        winner = team_b_id

    return MatchResult(
        tournament_id=tournament_id,
        round_number=1,
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        team_a_scores=team_a_scores,
        team_b_scores=team_b_scores,
        team_a_total=total_a,
        team_b_total=total_b,
        winner_team_id=winner,
        is_draw=is_draw,
    )
```

Add the `_inject_hidden_tests` method to `JudgeService`:

```python
async def _inject_hidden_tests(self, workspace: str, hidden_src: Path) -> str:
    """Copy hidden test files into team workspace. Returns path to copied tests."""
    target_dir = Path(workspace) / "hidden_tests"
    target_dir.mkdir(parents=True, exist_ok=True)

    if hidden_src.is_dir():
        import shutil
        for test_file in hidden_src.iterdir():
            if test_file.is_file():
                shutil.copy2(test_file, target_dir / test_file.name)
        logger.info("Injected hidden tests from %s into %s", hidden_src, target_dir)
        return str(target_dir)

    logger.warning("No hidden tests found at %s, using team's own tests", hidden_src)
    return f"{workspace}/tests"
```

- [ ] **Step 2: Commit**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
git add packages/judge/src/scoring/service.py
git commit -m "feat(judge): inject hidden tests into workspace before scoring

Copies challenge hidden_tests/ into each team's workspace so pytest
can resolve imports against the team's src/ directory."
```

---

### Task 11: Update API Route for Strategy-Based Config

**Files:**
- Modify: `packages/api/src/routes/tournaments.py`

- [ ] **Step 1: Update create_tournament endpoint**

The `TournamentConfig` model now expects `teams: list[TeamStrategy]` instead of `list[TeamConfig]`. The API route at `packages/api/src/routes/tournaments.py` already uses `TournamentConfig.model_validate(payload)` (line 130), so it will automatically accept the new schema.

The only change needed is updating the `_tournament_to_response` helper to work with `TeamStrategy` instead of `TeamConfig` for team summaries (line 48-95):

```python
def _tournament_to_response(
    tournament: Tournament,
) -> TournamentResponse:
    """Convert a domain Tournament entity to a TournamentResponse."""
    team_summaries = []
    for i, tid in enumerate(tournament.team_ids):
        strategy = tournament.config.teams[i] if i < len(tournament.config.teams) else None
        team_summaries.append(
            TeamSummary(
                id=tid,
                name=strategy.name if strategy else f"team-{tid}",
                agent_count=1,  # One Claude Code CLI per team
                total_cost_usd=0.0,
            )
        )

    return TournamentResponse(
        id=tournament.id,
        format=tournament.format,
        current_phase=tournament.current_phase,
        challenge_id=tournament.challenge_id,
        teams=team_summaries,
        total_cost_usd=tournament.total_cost_usd,
        started_at=tournament.started_at,
        completed_at=tournament.completed_at,
        winner_team_id=tournament.winner_team_id,
    )
```

Also update the `start_tournament` docstring/description (line 219) from "RESEARCH phase" to "BUILD phase".

- [ ] **Step 2: Commit**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
git add packages/api/src/routes/tournaments.py
git commit -m "feat(api): update tournament routes for strategy-based teams

Accept TeamStrategy in tournament creation. Team summaries use
strategy name instead of agent counts."
```

---

### Task 12: Update API Main to Wire RunnerManager

**Files:**
- Modify: `packages/api/src/main.py`
- Modify: `packages/api/src/dependencies.py`

- [ ] **Step 1: Read and update dependencies.py**

Read `packages/api/src/dependencies.py` to understand current wiring, then update it to create `RunnerManager` instead of `AgentTeamManager`:

Replace the `AgentTeamManager` initialization with:

```python
from packages.agents.src.runner.manager import RunnerManager

runner_manager = RunnerManager(event_bus=event_bus)
```

And pass it to the orchestrator:

```python
orchestrator = TournamentOrchestrator(
    event_bus=event_bus,
    sandbox_manager=sandbox_manager,
    runner_manager=runner_manager,
    judge_service=judge_service,
)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
git add packages/api/src/main.py packages/api/src/dependencies.py
git commit -m "feat(api): wire RunnerManager into dependency injection

Orchestrator now receives RunnerManager instead of AgentTeamManager."
```

---

### Task 13: Update CLAUDE.md Files

**Files:**
- Modify: `CLAUDE.md` (root)
- Modify: `packages/agents/CLAUDE.md`
- Modify: `packages/core/CLAUDE.md`

- [ ] **Step 1: Update packages/agents/CLAUDE.md**

Replace the content to document the new runner architecture:

```markdown
# packages/agents — CLAUDE.md

## What This Package Is
Claude Code CLI runner management. Spawns real Claude Code CLI sessions
inside Docker sandboxes, streams their output, and manages lifecycle.

## Key Modules
- `src/runner/claude_code.py` — ClaudeCodeRunner: spawns and manages one CLI process
- `src/runner/manager.py` — RunnerManager: manages multiple runners across teams
- `src/runner/strategies.py` — Built-in strategy definitions (architecture-first, tdd-first, etc.)
- `src/runner/prompt.py` — Builds initial prompt from challenge + strategy
- `src/runner/stream_parser.py` — Parses Claude Code stream-json output into typed events
- `src/self_config/bootstrap.py` — Optional project bootstrapper (can pre-seed minimal files)
- `src/communication/mailbox.py` — Redis mailbox (kept for future multi-agent experiments)

## How It Works
1. Orchestrator calls `RunnerManager.start_team(team_id, workspace, strategy, challenge_path)`
2. RunnerManager creates a `ClaudeCodeRunner` for the team
3. ClaudeCodeRunner spawns `claude --output-format stream-json --dangerously-skip-permissions -p "..."`
4. The CLI runs autonomously: reads challenge, self-configures, builds, tests, fixes
5. Stream parser reads stdout events and forwards them to Redis Pub/Sub for spectators
6. Orchestrator calls `stop_team()` when BUILD phase times out

## Strategies
| Name | Model | Approach |
|------|-------|----------|
| architecture-first | Opus 4.6 | Design before code, ADRs first |
| tdd-first | Sonnet 4.6 | Tests before implementation |
| speed-run | Sonnet 4.6 | Ship fast, test later |
| balanced | Sonnet 4.6 | Iterative: design → code → test |

## Dependencies
- `packages/shared` — Types, events, config
```

- [ ] **Step 2: Update packages/core/CLAUDE.md**

Update to reflect simplified phases:

```markdown
# packages/core — CLAUDE.md

## What This Package Is
The tournament orchestration engine. Manages the full lifecycle:
tournament creation → sandbox provisioning → CLI execution → judging → results.

## Key Modules
- `src/tournament/orchestrator.py` — Main orchestrator (simplified phase state machine)
- `src/elo/calculator.py` — Bradley-Terry ELO implementation

## Simplified Phase Machine
```
PREP → BUILD → CROSS_REVIEW → FIX → JUDGE → COMPLETE
```
- **PREP** (2 min): Create sandboxes, write challenge
- **BUILD** (configurable, default 30 min): Claude Code CLIs run autonomously
- **CROSS_REVIEW** (10 min): Read-only access to opponent workspace
- **FIX** (10 min): Address review feedback
- **JUDGE** (5 min): Stop CLIs, run hidden tests, score
- **COMPLETE**: Publish results, update ELO

## Dependencies
- `packages/shared` — Types, DB, events, config
- `packages/sandbox` — Sandbox creation/teardown
- `packages/agents` — RunnerManager for Claude Code CLI execution
```

- [ ] **Step 3: Update root CLAUDE.md core loop**

In the root `CLAUDE.md`, update the "Core Loop" to:
```
Challenge → Sandbox → Claude Code CLI (autonomous) → Cross-Review → Judge → Winner
```

And update the Architecture section to mention RunnerManager instead of AgentTeamManager.

- [ ] **Step 4: Commit**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
git add CLAUDE.md packages/agents/CLAUDE.md packages/core/CLAUDE.md
git commit -m "docs: update CLAUDE.md files for autonomous execution architecture

Document ClaudeCodeRunner, simplified phases, strategy system.
Core loop: Challenge → Sandbox → CLI (autonomous) → Judge → Winner."
```

---

### Task 14: Run All Tests and Verify

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
python -m pytest packages/ -v --tb=short 2>&1 | head -100
```

Expected: All new tests pass. Any pre-existing tests that depend on `TeamConfig.agents` will need updating — fix import errors.

- [ ] **Step 2: Fix any broken imports**

If existing tests reference `TeamConfig.agents`, `TournamentPhase.RESEARCH`, or `TournamentPhase.ARCHITECTURE`, update them to use the new types.

Key areas to check:
- `packages/api/tests/test_tournament_routes.py` — may reference old `TeamConfig`
- `packages/core/tests/` — may reference old phase names
- `packages/shared/tests/` — may validate old `TournamentPhase` values

- [ ] **Step 3: Run ruff check**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
ruff check packages/agents/src/runner/ packages/core/src/tournament/orchestrator.py packages/judge/src/scoring/service.py --fix
ruff format packages/agents/src/runner/ packages/core/src/tournament/ packages/judge/src/scoring/
```

- [ ] **Step 4: Final commit**

```bash
cd /Users/yashbishnoi/Downloads/agentforge-arena
git add -A
git commit -m "chore: fix imports and lint for autonomous execution refactor"
```
