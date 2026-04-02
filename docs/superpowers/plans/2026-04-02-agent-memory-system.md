# Agent Memory System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 3-layer persistent memory system (`packages/memory/`) that enables agents to survive 48-72h multi-day tournament builds by persisting working state (Redis), structured knowledge (PostgreSQL+pgvector), and semantic code search (Qdrant+FastEmbed+tree-sitter).

**Architecture:** New `packages/memory/` with MemoryManager facade exposing `recall()`/`record()`. L1 = per-agent Redis Hash+JSON. L2 = per-team PostgreSQL table with pgvector HNSW + GIN full-text. L3 = per-team Qdrant collection with named vectors + sparse BM25. Compression engine uses Haiku 4.5 for summarization + deterministic keyword promotion. DocumentSyncer routes promoted records to all project `.md` files.

**Tech Stack:** Python 3.12, redis.asyncio, SQLAlchemy 2.0 async + pgvector, qdrant-client, fastembed, tree-sitter, Pydantic v2

**Spec:** `docs/superpowers/specs/2026-04-02-agent-memory-system-design.md`

---

## File Map

### New Files (packages/memory/)

| File | Responsibility |
|------|---------------|
| `packages/memory/__init__.py` | Package root |
| `packages/memory/CLAUDE.md` | Package docs for agents |
| `packages/memory/src/__init__.py` | Source root with public exports |
| `packages/memory/src/manager.py` | `MemoryManager` facade — single entry point |
| `packages/memory/src/working/__init__.py` | Working memory subpackage |
| `packages/memory/src/working/models.py` | `WorkingState` Pydantic model |
| `packages/memory/src/working/store.py` | `WorkingMemoryStore` — Redis Hash + JSON ops |
| `packages/memory/src/module/__init__.py` | Module memory subpackage |
| `packages/memory/src/module/models.py` | `RecordType`, `ModuleRecord` Pydantic models |
| `packages/memory/src/module/store.py` | `ModuleMemoryStore` — PostgreSQL + pgvector CRUD |
| `packages/memory/src/module/queries.py` | Hybrid SQL + vector query builders |
| `packages/memory/src/semantic/__init__.py` | Semantic memory subpackage |
| `packages/memory/src/semantic/models.py` | `CodeChunk`, `SearchResult`, `MemoryContext` |
| `packages/memory/src/semantic/store.py` | `SemanticStore` — Qdrant upsert/search/delete |
| `packages/memory/src/semantic/embedder.py` | `HybridEmbedder` — FastEmbed bulk + LiteLLM query |
| `packages/memory/src/indexer/__init__.py` | Indexer subpackage |
| `packages/memory/src/indexer/watcher.py` | `CodebaseWatcher` — debounced 60s mtime scan |
| `packages/memory/src/indexer/parser.py` | `CodeParser` — tree-sitter chunk extraction |
| `packages/memory/src/indexer/grammars.py` | `GrammarLoader` — lazy per-language grammar loading |
| `packages/memory/src/indexer/pipeline.py` | `IndexingPipeline` — parse -> embed -> upsert |
| `packages/memory/src/compression/__init__.py` | Compression subpackage |
| `packages/memory/src/compression/compressor.py` | `ContextCompressor` — Haiku 4.5 summarization |
| `packages/memory/src/compression/promoter.py` | `MemoryPromoter` — deterministic L1->L2 keyword rules |
| `packages/memory/src/compression/doc_sync.py` | `DocumentSyncer` — route L2 records to .md files |
| `packages/memory/tests/__init__.py` | Test package |
| `packages/memory/tests/conftest.py` | Shared fixtures (fakeredis, mock Qdrant, factories) |
| `packages/memory/tests/unit/test_working_store.py` | L1 store tests |
| `packages/memory/tests/unit/test_module_store.py` | L2 store tests |
| `packages/memory/tests/unit/test_semantic_store.py` | L3 store tests |
| `packages/memory/tests/unit/test_parser.py` | Tree-sitter parser tests |
| `packages/memory/tests/unit/test_grammars.py` | Grammar loader tests |
| `packages/memory/tests/unit/test_embedder.py` | Embedder tests |
| `packages/memory/tests/unit/test_compressor.py` | Compressor tests |
| `packages/memory/tests/unit/test_promoter.py` | Promoter tests |
| `packages/memory/tests/unit/test_doc_sync.py` | DocumentSyncer tests |
| `packages/memory/tests/integration/test_memory_manager.py` | Full recall/record/overflow integration test |
| `packages/memory/tests/integration/test_indexer_pipeline.py` | Parse -> embed -> upsert end-to-end test |

### Modified Files

| File | Change |
|------|--------|
| `pyproject.toml` | Add 5 new dependencies |
| `packages/agents/src/teams/manager.py` | Wire MemoryManager into AgentProcess + AgentTeamManager |
| `packages/api/src/main.py` | Initialize MemoryManager factory in lifespan |

---

## Task 1: Add Dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml:10-63` (dependencies section)

- [ ] **Step 1: Add memory system dependencies**

In `pyproject.toml`, add these 5 lines to the `dependencies` array, after the existing `"claude-agent-sdk>=0.1.0"` line:

```toml
    # Agent Memory System
    "fastembed>=0.5.0",
    "tree-sitter>=0.25.0",
    "tree-sitter-python>=0.25.0",
    "tree-sitter-javascript>=0.25.0",
    "tree-sitter-typescript>=0.25.0",
```

- [ ] **Step 2: Verify the dependency list parses**

Run: `python -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']"`
Expected: No errors, prints the dependency list

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat(memory): add fastembed and tree-sitter dependencies"
```

---

## Task 2: Package Scaffolding + CLAUDE.md

**Files:**
- Create: `packages/memory/__init__.py`
- Create: `packages/memory/CLAUDE.md`
- Create: `packages/memory/src/__init__.py`
- Create: `packages/memory/src/working/__init__.py`
- Create: `packages/memory/src/module/__init__.py`
- Create: `packages/memory/src/semantic/__init__.py`
- Create: `packages/memory/src/indexer/__init__.py`
- Create: `packages/memory/src/compression/__init__.py`
- Create: `packages/memory/tests/__init__.py`
- Create: `packages/memory/tests/unit/__init__.py`
- Create: `packages/memory/tests/integration/__init__.py`

- [ ] **Step 1: Create all __init__.py files**

Create `packages/memory/__init__.py`:
```python
"""AgentForge Arena — Agent Memory System."""
```

Create `packages/memory/src/__init__.py`:
```python
"""Agent Memory System — 3-layer persistent memory for tournament agents."""
```

Create `packages/memory/src/working/__init__.py`:
```python
"""L1: Working Memory — Redis Hash + JSON per-agent state."""
```

Create `packages/memory/src/module/__init__.py`:
```python
"""L2: Module Memory — PostgreSQL + pgvector structured records."""
```

Create `packages/memory/src/semantic/__init__.py`:
```python
"""L3: Semantic Memory — Qdrant + FastEmbed + tree-sitter code search."""
```

Create `packages/memory/src/indexer/__init__.py`:
```python
"""Code Indexer — tree-sitter parsing + embedding pipeline."""
```

Create `packages/memory/src/compression/__init__.py`:
```python
"""Compression — Haiku summarization + deterministic promotion + doc sync."""
```

Create `packages/memory/tests/__init__.py`:
```python
"""Tests for packages/memory."""
```

Create `packages/memory/tests/unit/__init__.py`:
```python
"""Unit tests for memory package."""
```

Create `packages/memory/tests/integration/__init__.py`:
```python
"""Integration tests for memory package."""
```

- [ ] **Step 2: Create CLAUDE.md**

Create `packages/memory/CLAUDE.md`:
```markdown
# packages/memory — CLAUDE.md

## What This Package Is
3-layer persistent memory system for tournament agents. Enables agents to survive
48-72h multi-day builds by persisting state, structured knowledge, and semantic
code search across context rotations and agent crashes.

## Key Modules
- `src/manager.py` — MemoryManager: single entry point with recall() and record()
- `src/working/store.py` — WorkingMemoryStore: Redis Hash + JSON per-agent state (L1)
- `src/module/store.py` — ModuleMemoryStore: PostgreSQL + pgvector structured records (L2)
- `src/semantic/store.py` — SemanticStore: Qdrant vector search over codebase (L3)
- `src/indexer/pipeline.py` — IndexingPipeline: tree-sitter parse -> FastEmbed -> Qdrant
- `src/indexer/watcher.py` — CodebaseWatcher: debounced 60s mtime-based re-index
- `src/compression/compressor.py` — ContextCompressor: Haiku 4.5 summarization
- `src/compression/promoter.py` — MemoryPromoter: deterministic L1 -> L2 keyword promotion
- `src/compression/doc_sync.py` — DocumentSyncer: route records to project .md files

## Three Layers
```
L1 (Redis)      — Per-agent working state. TTL = sprint. <1ms read/write.
L2 (PostgreSQL) — Per-team structured records. TTL = tournament. Hybrid SQL + vector search.
L3 (Qdrant)     — Per-team code search. TTL = tournament. Named vectors + sparse BM25.
```

## Core API
```python
context = await memory.recall(agent_id, role, query)  # Before LLM call
await memory.record(agent_id, role, task=..., decision=...)  # After LLM call
```

## Dependencies
- `packages/shared` — Types (AgentRole, TournamentPhase), DB, config, LLM client
```

- [ ] **Step 3: Commit**

```bash
git add packages/memory/
git commit -m "feat(memory): scaffold package structure with CLAUDE.md"
```

---

## Task 3: Data Models — Working State (L1)

**Files:**
- Create: `packages/memory/src/working/models.py`
- Test: `packages/memory/tests/unit/test_working_models.py`

- [ ] **Step 1: Write the failing test**

Create `packages/memory/tests/unit/test_working_models.py`:
```python
"""Tests for L1 Working Memory models."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from packages.memory.src.working.models import WorkingState
from packages.shared.src.types.models import AgentRole, TournamentPhase


class TestWorkingState:
    """Tests for WorkingState Pydantic model."""

    def test_create_minimal_working_state(self) -> None:
        """Minimal WorkingState should have sensible defaults."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
        )
        assert state.current_task is None
        assert state.current_file is None
        assert state.recent_decisions == []
        assert state.recent_files_touched == []
        assert state.active_errors == []
        assert state.context_summary == ""
        assert state.token_budget_used == 0

    def test_recent_decisions_capped_at_10(self) -> None:
        """recent_decisions should not exceed 10 entries."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.ARCHITECT,
            current_phase=TournamentPhase.ARCHITECTURE,
            recent_decisions=[f"decision-{i}" for i in range(15)],
        )
        assert len(state.recent_decisions) == 10

    def test_recent_files_capped_at_20(self) -> None:
        """recent_files_touched should not exceed 20 entries."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            recent_files_touched=[f"src/file_{i}.py" for i in range(25)],
        )
        assert len(state.recent_files_touched) == 20

    def test_active_errors_uncapped(self) -> None:
        """active_errors should have no cap."""
        errors = [f"Error {i}" for i in range(100)]
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.TESTER,
            current_phase=TournamentPhase.BUILD,
            active_errors=errors,
        )
        assert len(state.active_errors) == 100

    def test_serialization_roundtrip(self) -> None:
        """WorkingState should survive JSON roundtrip."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            current_task="Build auth API",
            recent_decisions=["Chose bcrypt"],
        )
        json_str = state.model_dump_json()
        restored = WorkingState.model_validate_json(json_str)
        assert restored.agent_id == state.agent_id
        assert restored.current_task == "Build auth API"
        assert restored.recent_decisions == ["Chose bcrypt"]

    def test_estimate_tokens_returns_positive_int(self) -> None:
        """estimate_tokens() should return a reasonable token count."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            current_task="Build the auth module",
            context_summary="We are building a FastAPI auth module with bcrypt.",
            recent_decisions=["Chose bcrypt over argon2"],
        )
        tokens = state.estimate_tokens()
        assert isinstance(tokens, int)
        assert tokens > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/memory/tests/unit/test_working_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'packages.memory.src.working.models'`

- [ ] **Step 3: Write the implementation**

Create `packages/memory/src/working/models.py`:
```python
"""L1 Working Memory — Pydantic models for per-agent Redis state."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.shared.src.types.models import AgentRole, TournamentPhase


class WorkingState(BaseModel):
    """Per-agent working memory stored in Redis Hash + JSON.

    Represents the hot state refreshed every LLM call.
    TTL: expires at sprint boundary or agent termination.
    """

    model_config = ConfigDict(strict=True)

    agent_id: UUID
    team_id: UUID
    role: AgentRole
    current_phase: TournamentPhase
    current_task: str | None = None
    current_file: str | None = None
    recent_decisions: list[str] = Field(default_factory=list, description="Capped at 10")
    recent_files_touched: list[str] = Field(default_factory=list, description="Capped at 20")
    active_errors: list[str] = Field(default_factory=list, description="Uncapped")
    context_summary: str = Field(default="", description="Compressed summary from overflow handler")
    token_budget_used: int = Field(default=0, ge=0)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def cap_lists(self) -> WorkingState:
        """Enforce list caps: decisions=10, files=20."""
        if len(self.recent_decisions) > 10:
            self.recent_decisions = self.recent_decisions[-10:]
        if len(self.recent_files_touched) > 20:
            self.recent_files_touched = self.recent_files_touched[-20:]
        return self

    def estimate_tokens(self) -> int:
        """Rough token estimate (~4 chars per token)."""
        text = self.model_dump_json()
        return max(1, len(text) // 4)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/memory/tests/unit/test_working_models.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/memory/src/working/models.py packages/memory/tests/unit/test_working_models.py
git commit -m "feat(memory): add WorkingState model with list caps and token estimation"
```

---

## Task 4: Data Models — Module Record + RecordType (L2)

**Files:**
- Create: `packages/memory/src/module/models.py`
- Test: `packages/memory/tests/unit/test_module_models.py`

- [ ] **Step 1: Write the failing test**

Create `packages/memory/tests/unit/test_module_models.py`:
```python
"""Tests for L2 Module Memory models."""

from __future__ import annotations

from uuid import uuid4

import pytest

from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.shared.src.types.models import AgentRole


class TestRecordType:
    """Tests for RecordType enum."""

    def test_all_10_record_types_exist(self) -> None:
        """RecordType should have exactly 10 members."""
        assert len(RecordType) == 10

    def test_record_type_values_are_snake_case(self) -> None:
        """All values should be lowercase snake_case."""
        for rt in RecordType:
            assert rt.value == rt.value.lower()
            assert " " not in rt.value


class TestModuleRecord:
    """Tests for ModuleRecord Pydantic model."""

    def test_create_adr_record(self) -> None:
        """Should create a valid ADR record."""
        record = ModuleRecord(
            team_id=uuid4(),
            tournament_id=uuid4(),
            record_type=RecordType.ADR,
            module_name="auth",
            title="Chose bcrypt over argon2",
            content="bcrypt — simpler API, well-supported.",
        )
        assert record.record_type == RecordType.ADR
        assert record.synced_to_docs is False
        assert record.id is not None

    def test_create_gotcha_record(self) -> None:
        """Should create a valid GOTCHA record."""
        record = ModuleRecord(
            team_id=uuid4(),
            tournament_id=uuid4(),
            record_type=RecordType.GOTCHA,
            module_name="cache",
            title="Redis drops idle connections",
            content="Wrap all Redis calls with tenacity retry.",
            agent_role=AgentRole.BUILDER,
        )
        assert record.record_type == RecordType.GOTCHA
        assert record.agent_role == AgentRole.BUILDER

    def test_serialization_roundtrip(self) -> None:
        """ModuleRecord should survive JSON roundtrip."""
        record = ModuleRecord(
            team_id=uuid4(),
            tournament_id=uuid4(),
            record_type=RecordType.CODING_PATTERN,
            module_name="api",
            title="Use Depends() for DI",
            content="Always use FastAPI Depends() for dependency injection.",
        )
        json_str = record.model_dump_json()
        restored = ModuleRecord.model_validate_json(json_str)
        assert restored.id == record.id
        assert restored.record_type == RecordType.CODING_PATTERN

    def test_metadata_defaults_to_empty_dict(self) -> None:
        """metadata should default to {}."""
        record = ModuleRecord(
            team_id=uuid4(),
            tournament_id=uuid4(),
            record_type=RecordType.FILE_META,
            module_name="main",
            title="Entry point",
            content="FastAPI app factory.",
        )
        assert record.metadata == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/memory/tests/unit/test_module_models.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `packages/memory/src/module/models.py`:
```python
"""L2 Module Memory — Pydantic models for structured PostgreSQL records."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from packages.shared.src.types.models import AgentRole


class RecordType(str, Enum):
    """Discriminator for module memory records."""

    FILE_META = "file_meta"
    ADR = "adr"
    TECH_DEBT = "tech_debt"
    SIGNATURE = "signature"
    ACTION_LOG = "action_log"
    DEPENDENCY = "dependency"
    GOTCHA = "gotcha"
    CODING_PATTERN = "coding_pattern"
    AGENT_LEARNING = "agent_learning"
    HOOK_DISCOVERY = "hook_discovery"


class ModuleRecord(BaseModel):
    """A structured memory record stored in PostgreSQL + pgvector.

    Scope: per-team. Survives agent crashes.
    TTL: tournament lifetime.
    """

    model_config = ConfigDict(strict=True)

    id: UUID = Field(default_factory=uuid4)
    team_id: UUID
    tournament_id: UUID
    record_type: RecordType
    module_name: str = Field(description="Logical module name, e.g., 'auth', 'api'")
    file_path: str | None = None
    title: str = Field(description="Short summary for display")
    content: str = Field(description="Full content of the record")
    metadata: dict[str, Any] = Field(default_factory=dict)
    agent_id: UUID | None = None
    agent_role: AgentRole | None = None
    synced_to_docs: bool = Field(default=False, description="True once DocumentSyncer processed")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/memory/tests/unit/test_module_models.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/memory/src/module/models.py packages/memory/tests/unit/test_module_models.py
git commit -m "feat(memory): add RecordType enum and ModuleRecord model"
```

---

## Task 5: Data Models — CodeChunk, SearchResult, MemoryContext (L3)

**Files:**
- Create: `packages/memory/src/semantic/models.py`
- Test: `packages/memory/tests/unit/test_semantic_models.py`

- [ ] **Step 1: Write the failing test**

Create `packages/memory/tests/unit/test_semantic_models.py`:
```python
"""Tests for L3 Semantic Memory models."""

from __future__ import annotations

from uuid import uuid4

import pytest

from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.semantic.models import CodeChunk, MemoryContext, SearchResult
from packages.memory.src.working.models import WorkingState
from packages.shared.src.types.models import AgentRole, TournamentPhase


class TestCodeChunk:
    """Tests for CodeChunk model."""

    def test_create_function_chunk(self) -> None:
        """Should create a valid function chunk."""
        chunk = CodeChunk(
            chunk_id="src/auth.py::login",
            file_path="src/auth.py",
            language="python",
            module_name="auth",
            symbol_name="login",
            symbol_type="function",
            content="def login(username: str, password: str) -> Token:\n    ...",
            line_start=10,
            line_end=25,
        )
        assert chunk.symbol_type == "function"
        assert chunk.dependencies == []

    def test_chunk_id_format(self) -> None:
        """chunk_id should be file_path::symbol_name."""
        chunk = CodeChunk(
            chunk_id="src/models.py::User",
            file_path="src/models.py",
            language="python",
            module_name="models",
            symbol_name="User",
            symbol_type="class",
            content="class User(BaseModel): ...",
            line_start=1,
            line_end=20,
        )
        assert "::" in chunk.chunk_id


class TestSearchResult:
    """Tests for SearchResult model."""

    def test_semantic_search_result(self) -> None:
        """Should create a search result from L3."""
        chunk = CodeChunk(
            chunk_id="src/auth.py::login",
            file_path="src/auth.py",
            language="python",
            module_name="auth",
            content="def login(): ...",
            line_start=1,
            line_end=5,
        )
        result = SearchResult(
            source="semantic",
            score=0.92,
            chunk=chunk,
            snippet="src/auth.py:1-5 login()",
        )
        assert result.source == "semantic"
        assert result.record is None

    def test_module_search_result(self) -> None:
        """Should create a search result from L2."""
        record = ModuleRecord(
            team_id=uuid4(),
            tournament_id=uuid4(),
            record_type=RecordType.ADR,
            module_name="auth",
            title="Chose bcrypt",
            content="bcrypt for password hashing.",
        )
        result = SearchResult(
            source="module",
            score=0.85,
            record=record,
            snippet="ADR: Chose bcrypt for password hashing.",
        )
        assert result.source == "module"
        assert result.chunk is None


class TestMemoryContext:
    """Tests for MemoryContext model."""

    def test_format_for_prompt_returns_string(self) -> None:
        """format_for_prompt() should return a non-empty string."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            current_task="Build auth",
        )
        ctx = MemoryContext(
            working_state=state,
            module_context=[],
            semantic_context=[],
            total_tokens_estimate=500,
        )
        prompt = ctx.format_for_prompt()
        assert isinstance(prompt, str)
        assert "Build auth" in prompt

    def test_total_tokens_reflects_all_layers(self) -> None:
        """total_tokens_estimate should be set correctly."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
        )
        ctx = MemoryContext(
            working_state=state,
            module_context=[],
            semantic_context=[],
            total_tokens_estimate=1234,
        )
        assert ctx.total_tokens_estimate == 1234
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/memory/tests/unit/test_semantic_models.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `packages/memory/src/semantic/models.py`:
```python
"""L3 Semantic Memory — Pydantic models for code search and memory context."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from packages.memory.src.module.models import ModuleRecord
from packages.memory.src.working.models import WorkingState


class CodeChunk(BaseModel):
    """A semantic chunk extracted from source code via tree-sitter.

    Each chunk is one function, class, method, or file section.
    Stored in Qdrant with named vectors (code, docstring) + sparse (keywords).
    """

    model_config = ConfigDict(strict=True)

    chunk_id: str = Field(description="'{file_path}::{symbol_name}' or '{file_path}::chunk_{n}'")
    file_path: str
    language: str
    module_name: str
    symbol_name: str | None = None
    symbol_type: str | None = Field(
        default=None,
        description="function, class, method, module",
    )
    content: str
    docstring: str | None = None
    line_start: int
    line_end: int
    dependencies: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """A single search result from L2 (module) or L3 (semantic)."""

    source: str = Field(description="'module' or 'semantic'")
    score: float = Field(ge=0.0, le=1.0)
    chunk: CodeChunk | None = None
    record: ModuleRecord | None = None
    snippet: str = Field(description="Formatted text for prompt injection")


class MemoryContext(BaseModel):
    """Combined context from all 3 memory layers. Returned by recall()."""

    working_state: WorkingState
    module_context: list[ModuleRecord]
    semantic_context: list[SearchResult]
    total_tokens_estimate: int

    def format_for_prompt(self) -> str:
        """Format all 3 layers into structured text for LLM prompt injection."""
        sections: list[str] = []

        # L1: Working state
        ws = self.working_state
        l1_lines = ["## Agent Memory Context"]
        if ws.current_task:
            l1_lines.append(f"**Current Task:** {ws.current_task}")
        if ws.current_file:
            l1_lines.append(f"**Current File:** {ws.current_file}")
        if ws.context_summary:
            l1_lines.append(f"**Summary:** {ws.context_summary}")
        if ws.recent_decisions:
            l1_lines.append("**Recent Decisions:**")
            for d in ws.recent_decisions:
                l1_lines.append(f"  - {d}")
        if ws.active_errors:
            l1_lines.append("**Active Errors:**")
            for e in ws.active_errors:
                l1_lines.append(f"  - {e}")
        sections.append("\n".join(l1_lines))

        # L2: Module context
        if self.module_context:
            l2_lines = ["### Relevant Knowledge"]
            for rec in self.module_context:
                l2_lines.append(
                    f"- [{rec.record_type.value}] {rec.title}: {rec.content[:200]}"
                )
            sections.append("\n".join(l2_lines))

        # L3: Semantic context
        if self.semantic_context:
            l3_lines = ["### Relevant Code"]
            for sr in self.semantic_context:
                l3_lines.append(f"- {sr.snippet}")
            sections.append("\n".join(l3_lines))

        return "\n\n".join(sections)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/memory/tests/unit/test_semantic_models.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/memory/src/semantic/models.py packages/memory/tests/unit/test_semantic_models.py
git commit -m "feat(memory): add CodeChunk, SearchResult, MemoryContext models"
```

---

## Task 6: L1 Working Memory Store (Redis)

**Files:**
- Create: `packages/memory/src/working/store.py`
- Test: `packages/memory/tests/unit/test_working_store.py`
- Create: `packages/memory/tests/conftest.py`

- [ ] **Step 1: Create shared test fixtures**

Create `packages/memory/tests/conftest.py`:
```python
"""Shared fixtures for memory package tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from packages.shared.src.types.models import AgentRole, TournamentPhase


@pytest.fixture()
def team_id():
    return uuid4()


@pytest.fixture()
def tournament_id():
    return uuid4()


@pytest.fixture()
def agent_id():
    return uuid4()


@pytest.fixture()
def mock_redis():
    """Create a mock async Redis client."""
    r = MagicMock()
    r.hset = AsyncMock()
    r.hgetall = AsyncMock(return_value={})
    r.delete = AsyncMock()
    r.expire = AsyncMock()
    r.set = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.exists = AsyncMock(return_value=0)
    return r


@pytest.fixture()
def mock_qdrant():
    """Create a mock QdrantClient."""
    client = MagicMock()
    client.upsert = AsyncMock()
    client.search = AsyncMock(return_value=[])
    client.delete = AsyncMock()
    client.create_collection = AsyncMock()
    client.collection_exists = AsyncMock(return_value=False)
    return client
```

- [ ] **Step 2: Write the failing test**

Create `packages/memory/tests/unit/test_working_store.py`:
```python
"""Tests for L1 WorkingMemoryStore (Redis)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import orjson
import pytest

from packages.memory.src.working.models import WorkingState
from packages.memory.src.working.store import WorkingMemoryStore
from packages.shared.src.types.models import AgentRole, TournamentPhase


@pytest.fixture()
def store(mock_redis, team_id) -> WorkingMemoryStore:
    return WorkingMemoryStore(redis=mock_redis, team_id=team_id)


@pytest.fixture()
def sample_state(agent_id, team_id) -> WorkingState:
    return WorkingState(
        agent_id=agent_id,
        team_id=team_id,
        role=AgentRole.BUILDER,
        current_phase=TournamentPhase.BUILD,
        current_task="Build auth API",
    )


class TestWorkingMemoryStore:
    """Tests for Redis-backed working memory."""

    def test_key_format(self, store, agent_id) -> None:
        """Redis key should follow working:{team_id}:{role} pattern."""
        key = store._state_key(AgentRole.BUILDER)
        assert "working:" in key
        assert "builder" in key

    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(
        self, store, mock_redis, agent_id, sample_state
    ) -> None:
        """save() then load() should return equivalent state."""
        # Configure mock to return what was saved
        saved_data = {}

        async def capture_set(key, value, **kwargs):
            saved_data["key"] = key
            saved_data["value"] = value

        mock_redis.set = AsyncMock(side_effect=capture_set)
        mock_redis.get = AsyncMock(
            side_effect=lambda key: saved_data.get("value")
        )

        await store.save(sample_state)
        mock_redis.set.assert_called_once()

        result = await store.load(AgentRole.BUILDER)
        assert result is not None
        assert result.current_task == "Build auth API"

    @pytest.mark.asyncio
    async def test_load_nonexistent_returns_none(self, store, mock_redis) -> None:
        """load() for non-existent agent should return None."""
        mock_redis.get = AsyncMock(return_value=None)
        result = await store.load(AgentRole.BUILDER)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_removes_key(self, store, mock_redis) -> None:
        """delete() should remove the Redis key."""
        await store.delete(AgentRole.BUILDER)
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_sets_ttl(self, store, mock_redis, sample_state) -> None:
        """save() should set TTL on the key."""
        await store.save(sample_state, ttl_seconds=3600)
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_exceeds_threshold_true_when_over(
        self, store, mock_redis, sample_state
    ) -> None:
        """exceeds_threshold() should return True when tokens > threshold."""
        # Create a state with a lot of content
        big_state = sample_state.model_copy(
            update={"context_summary": "x" * 10000}
        )
        data = big_state.model_dump_json().encode()
        mock_redis.get = AsyncMock(return_value=data)
        result = await store.exceeds_threshold(AgentRole.BUILDER, threshold=2000)
        assert result is True

    @pytest.mark.asyncio
    async def test_exceeds_threshold_false_when_under(
        self, store, mock_redis, sample_state
    ) -> None:
        """exceeds_threshold() should return False when tokens < threshold."""
        data = sample_state.model_dump_json().encode()
        mock_redis.get = AsyncMock(return_value=data)
        result = await store.exceeds_threshold(AgentRole.BUILDER, threshold=2000)
        assert result is False
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest packages/memory/tests/unit/test_working_store.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Write the implementation**

Create `packages/memory/src/working/store.py`:
```python
"""L1 Working Memory Store — Redis Hash + JSON per-agent state."""

from __future__ import annotations

import logging
from uuid import UUID

import redis.asyncio as aioredis

from packages.memory.src.working.models import WorkingState
from packages.shared.src.types.models import AgentRole

logger = logging.getLogger(__name__)


class WorkingMemoryStore:
    """Per-agent working memory backed by Redis.

    Each agent gets a single Redis key containing its full WorkingState
    serialized as JSON. This is simpler than Hash + JSON split and sufficient
    since we always read/write the full state atomically.
    """

    KEY_PREFIX = "working"

    def __init__(self, redis: aioredis.Redis, team_id: UUID) -> None:
        self._redis = redis
        self._team_id = team_id

    def _state_key(self, role: AgentRole) -> str:
        """Redis key for an agent's working state."""
        return f"{self.KEY_PREFIX}:{self._team_id}:{role.value}"

    async def save(self, state: WorkingState, *, ttl_seconds: int | None = None) -> None:
        """Persist working state to Redis."""
        key = self._state_key(state.role)
        data = state.model_dump_json().encode()
        await self._redis.set(key, data)
        if ttl_seconds is not None:
            await self._redis.expire(key, ttl_seconds)
        logger.debug("Saved working state for %s (%d bytes)", state.role.value, len(data))

    async def load(self, role: AgentRole) -> WorkingState | None:
        """Load working state from Redis. Returns None if not found."""
        key = self._state_key(role)
        data = await self._redis.get(key)
        if data is None:
            return None
        return WorkingState.model_validate_json(data)

    async def delete(self, role: AgentRole) -> None:
        """Delete working state for an agent."""
        key = self._state_key(role)
        await self._redis.delete(key)
        logger.debug("Deleted working state for %s", role.value)

    async def exceeds_threshold(self, role: AgentRole, *, threshold: int = 2000) -> bool:
        """Check if working state exceeds the token threshold for compression."""
        key = self._state_key(role)
        data = await self._redis.get(key)
        if data is None:
            return False
        state = WorkingState.model_validate_json(data)
        return state.estimate_tokens() > threshold

    async def clear_team(self) -> None:
        """Delete all working memory keys for this team."""
        for role in AgentRole:
            await self.delete(role)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest packages/memory/tests/unit/test_working_store.py -v`
Expected: All 7 tests PASS

- [ ] **Step 6: Commit**

```bash
git add packages/memory/src/working/store.py packages/memory/tests/conftest.py packages/memory/tests/unit/test_working_store.py
git commit -m "feat(memory): implement L1 WorkingMemoryStore with Redis backend"
```

---

## Task 7: L2 Module Memory Store (PostgreSQL + pgvector)

**Files:**
- Create: `packages/memory/src/module/store.py`
- Create: `packages/memory/src/module/queries.py`
- Test: `packages/memory/tests/unit/test_module_store.py`

- [ ] **Step 1: Write the failing test**

Create `packages/memory/tests/unit/test_module_store.py`:
```python
"""Tests for L2 ModuleMemoryStore (PostgreSQL + pgvector)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.module.store import ModuleMemoryStore
from packages.shared.src.types.models import AgentRole


@pytest.fixture()
def mock_session():
    """Create a mock async SQLAlchemy session."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture()
def mock_session_factory(mock_session):
    """Create a mock session context manager factory."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def factory():
        yield mock_session

    return factory


@pytest.fixture()
def store(mock_session_factory, team_id, tournament_id) -> ModuleMemoryStore:
    return ModuleMemoryStore(
        session_factory=mock_session_factory,
        team_id=team_id,
        tournament_id=tournament_id,
    )


@pytest.fixture()
def sample_record(team_id, tournament_id) -> ModuleRecord:
    return ModuleRecord(
        team_id=team_id,
        tournament_id=tournament_id,
        record_type=RecordType.ADR,
        module_name="auth",
        title="Chose bcrypt",
        content="bcrypt for password hashing — simpler API.",
        agent_role=AgentRole.BUILDER,
    )


class TestModuleMemoryStore:
    """Tests for PostgreSQL-backed module memory."""

    @pytest.mark.asyncio
    async def test_insert_record(self, store, mock_session, sample_record) -> None:
        """insert() should add a record to the session."""
        await store.insert(sample_record)
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_insert_batch(self, store, mock_session, team_id, tournament_id) -> None:
        """insert_batch() should add multiple records."""
        records = [
            ModuleRecord(
                team_id=team_id,
                tournament_id=tournament_id,
                record_type=RecordType.GOTCHA,
                module_name="cache",
                title=f"Gotcha {i}",
                content=f"Content {i}",
            )
            for i in range(3)
        ]
        await store.insert_batch(records)
        assert mock_session.add.call_count == 3

    @pytest.mark.asyncio
    async def test_get_by_type(self, store, mock_session) -> None:
        """get_by_type() should query with correct record_type filter."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        mock_session.execute = AsyncMock(return_value=mock_result)

        results = await store.get_by_type(RecordType.ADR)
        assert isinstance(results, list)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_unsynced(self, store, mock_session) -> None:
        """get_unsynced() should return records where synced_to_docs=False."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        mock_session.execute = AsyncMock(return_value=mock_result)

        results = await store.get_unsynced()
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_mark_synced(self, store, mock_session) -> None:
        """mark_synced() should update synced_to_docs to True."""
        record_ids = [uuid4(), uuid4()]
        mock_session.execute = AsyncMock()
        await store.mark_synced(record_ids)
        mock_session.execute.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/memory/tests/unit/test_module_store.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the query builder**

Create `packages/memory/src/module/queries.py`:
```python
"""Hybrid SQL + vector query builders for L2 module memory."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, and_, func, select, text, update
from sqlalchemy.orm import Session

from packages.memory.src.module.models import RecordType


def select_by_type(
    team_id: UUID,
    record_type: RecordType,
    *,
    limit: int = 50,
) -> Select:
    """Build query to select records by type for a team."""
    from packages.memory.src.module.store import ModuleMemoryDB

    return (
        select(ModuleMemoryDB)
        .where(
            and_(
                ModuleMemoryDB.team_id == team_id,
                ModuleMemoryDB.record_type == record_type.value,
            )
        )
        .order_by(ModuleMemoryDB.created_at.desc())
        .limit(limit)
    )


def select_by_module(
    team_id: UUID,
    module_name: str,
    *,
    limit: int = 20,
) -> Select:
    """Build query to select records for a specific module."""
    from packages.memory.src.module.store import ModuleMemoryDB

    return (
        select(ModuleMemoryDB)
        .where(
            and_(
                ModuleMemoryDB.team_id == team_id,
                ModuleMemoryDB.module_name == module_name,
            )
        )
        .order_by(ModuleMemoryDB.created_at.desc())
        .limit(limit)
    )


def select_unsynced(team_id: UUID) -> Select:
    """Build query to select records not yet synced to docs."""
    from packages.memory.src.module.store import ModuleMemoryDB

    return (
        select(ModuleMemoryDB)
        .where(
            and_(
                ModuleMemoryDB.team_id == team_id,
                ModuleMemoryDB.synced_to_docs == False,  # noqa: E712
            )
        )
        .order_by(ModuleMemoryDB.created_at.asc())
    )


def update_synced(record_ids: list[UUID]) -> update:
    """Build update statement to mark records as synced."""
    from packages.memory.src.module.store import ModuleMemoryDB

    return (
        update(ModuleMemoryDB)
        .where(ModuleMemoryDB.id.in_(record_ids))
        .values(synced_to_docs=True)
    )


def select_fulltext(team_id: UUID, query: str, *, limit: int = 10) -> Select:
    """Build full-text search query using ts_vector."""
    from packages.memory.src.module.store import ModuleMemoryDB

    ts_query = func.plainto_tsquery("english", query)
    return (
        select(ModuleMemoryDB)
        .where(
            and_(
                ModuleMemoryDB.team_id == team_id,
                ModuleMemoryDB.ts_vector.op("@@")(ts_query),
            )
        )
        .order_by(func.ts_rank(ModuleMemoryDB.ts_vector, ts_query).desc())
        .limit(limit)
    )
```

- [ ] **Step 4: Write the store implementation**

Create `packages/memory/src/module/store.py`:
```python
"""L2 Module Memory Store — PostgreSQL + pgvector structured records."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, String, Text, func, update
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.module.queries import (
    select_by_module,
    select_by_type,
    select_fulltext,
    select_unsynced,
    update_synced,
)
from packages.shared.src.db.base import Base

logger = logging.getLogger(__name__)


class ModuleMemoryDB(Base):
    """SQLAlchemy ORM model for module_memory table."""

    __tablename__ = "module_memory"

    team_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    tournament_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    record_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    module_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    agent_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    synced_to_docs: Mapped[bool] = mapped_column(Boolean, default=False)
    ts_vector = mapped_column(
        Text,
        nullable=True,
    )  # Will be populated by trigger/manual update
    embedding = mapped_column(Vector(384), nullable=True)


# Type alias for session factory
SessionFactory = Callable[[], asynccontextmanager[AsyncGenerator[AsyncSession, None]]]


class ModuleMemoryStore:
    """CRUD operations for L2 module memory in PostgreSQL."""

    def __init__(
        self,
        session_factory: Any,
        team_id: UUID,
        tournament_id: UUID,
    ) -> None:
        self._session_factory = session_factory
        self._team_id = team_id
        self._tournament_id = tournament_id

    def _to_db(self, record: ModuleRecord) -> ModuleMemoryDB:
        """Convert Pydantic model to SQLAlchemy ORM instance."""
        return ModuleMemoryDB(
            id=record.id,
            team_id=record.team_id,
            tournament_id=record.tournament_id,
            record_type=record.record_type.value,
            module_name=record.module_name,
            file_path=record.file_path,
            title=record.title,
            content=record.content,
            metadata_json=record.metadata,
            agent_id=record.agent_id,
            agent_role=record.agent_role.value if record.agent_role else None,
            synced_to_docs=record.synced_to_docs,
        )

    def _from_db(self, row: ModuleMemoryDB) -> ModuleRecord:
        """Convert SQLAlchemy ORM instance to Pydantic model."""
        from packages.shared.src.types.models import AgentRole

        return ModuleRecord(
            id=row.id,
            team_id=row.team_id,
            tournament_id=row.tournament_id,
            record_type=RecordType(row.record_type),
            module_name=row.module_name,
            file_path=row.file_path,
            title=row.title,
            content=row.content,
            metadata=row.metadata_json,
            agent_id=row.agent_id,
            agent_role=AgentRole(row.agent_role) if row.agent_role else None,
            synced_to_docs=row.synced_to_docs,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def insert(self, record: ModuleRecord) -> None:
        """Insert a single record."""
        async with self._session_factory() as session:
            session.add(self._to_db(record))
            await session.flush()

    async def insert_batch(self, records: list[ModuleRecord]) -> None:
        """Insert multiple records in one transaction."""
        async with self._session_factory() as session:
            for record in records:
                session.add(self._to_db(record))
            await session.flush()

    async def get_by_type(
        self, record_type: RecordType, *, limit: int = 50
    ) -> list[ModuleRecord]:
        """Get records by type for this team."""
        async with self._session_factory() as session:
            stmt = select_by_type(self._team_id, record_type, limit=limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._from_db(row) for row in rows]

    async def get_by_module(
        self, module_name: str, *, limit: int = 20
    ) -> list[ModuleRecord]:
        """Get records for a specific module."""
        async with self._session_factory() as session:
            stmt = select_by_module(self._team_id, module_name, limit=limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._from_db(row) for row in rows]

    async def get_unsynced(self) -> list[ModuleRecord]:
        """Get records not yet synced to docs."""
        async with self._session_factory() as session:
            stmt = select_unsynced(self._team_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._from_db(row) for row in rows]

    async def mark_synced(self, record_ids: list[UUID]) -> None:
        """Mark records as synced to docs."""
        if not record_ids:
            return
        async with self._session_factory() as session:
            stmt = update_synced(record_ids)
            await session.execute(stmt)

    async def search_fulltext(self, query: str, *, limit: int = 10) -> list[ModuleRecord]:
        """Full-text search across module records."""
        async with self._session_factory() as session:
            stmt = select_fulltext(self._team_id, query, limit=limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._from_db(row) for row in rows]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest packages/memory/tests/unit/test_module_store.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add packages/memory/src/module/store.py packages/memory/src/module/queries.py packages/memory/tests/unit/test_module_store.py
git commit -m "feat(memory): implement L2 ModuleMemoryStore with PostgreSQL + pgvector"
```

---

## Task 8: L3 Semantic Store (Qdrant)

**Files:**
- Create: `packages/memory/src/semantic/store.py`
- Test: `packages/memory/tests/unit/test_semantic_store.py`

- [ ] **Step 1: Write the failing test**

Create `packages/memory/tests/unit/test_semantic_store.py`:
```python
"""Tests for L3 SemanticStore (Qdrant)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from packages.memory.src.semantic.models import CodeChunk, SearchResult
from packages.memory.src.semantic.store import SemanticStore


@pytest.fixture()
def store(mock_qdrant, team_id) -> SemanticStore:
    mock_embedder = MagicMock()
    mock_embedder.embed_query = AsyncMock(return_value=[0.1] * 384)
    return SemanticStore(
        qdrant=mock_qdrant,
        embedder=mock_embedder,
        team_id=team_id,
    )


@pytest.fixture()
def sample_chunks() -> list[CodeChunk]:
    return [
        CodeChunk(
            chunk_id="src/auth.py::login",
            file_path="src/auth.py",
            language="python",
            module_name="auth",
            symbol_name="login",
            symbol_type="function",
            content="def login(user, pw): ...",
            line_start=1,
            line_end=10,
        ),
        CodeChunk(
            chunk_id="src/auth.py::logout",
            file_path="src/auth.py",
            language="python",
            module_name="auth",
            symbol_name="logout",
            symbol_type="function",
            content="def logout(token): ...",
            line_start=12,
            line_end=20,
        ),
    ]


class TestSemanticStore:
    """Tests for Qdrant-backed semantic search."""

    def test_collection_name(self, store, team_id) -> None:
        """Collection name should include team_id."""
        assert str(team_id) in store.collection_name

    @pytest.mark.asyncio
    async def test_ensure_collection_creates_if_missing(
        self, store, mock_qdrant
    ) -> None:
        """ensure_collection() should create collection if it doesn't exist."""
        mock_qdrant.collection_exists = AsyncMock(return_value=False)
        await store.ensure_collection()
        mock_qdrant.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_collection_skips_if_exists(
        self, store, mock_qdrant
    ) -> None:
        """ensure_collection() should skip if collection exists."""
        mock_qdrant.collection_exists = AsyncMock(return_value=True)
        await store.ensure_collection()
        mock_qdrant.create_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_chunks(
        self, store, mock_qdrant, sample_chunks
    ) -> None:
        """upsert() should call Qdrant upsert with correct data."""
        mock_embedder = store._embedder
        mock_embedder.embed_bulk = AsyncMock(return_value=[[0.1] * 384, [0.2] * 384])
        await store.upsert(sample_chunks)
        mock_qdrant.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_returns_results(self, store, mock_qdrant) -> None:
        """search() should return SearchResult list."""
        # Mock Qdrant search response
        mock_point = MagicMock()
        mock_point.id = "src/auth.py::login"
        mock_point.score = 0.92
        mock_point.payload = {
            "file_path": "src/auth.py",
            "language": "python",
            "module_name": "auth",
            "symbol_name": "login",
            "symbol_type": "function",
            "content": "def login(): ...",
            "line_start": 1,
            "line_end": 10,
        }
        mock_qdrant.search = AsyncMock(return_value=[mock_point])

        results = await store.search("login function", limit=5)
        assert len(results) == 1
        assert results[0].source == "semantic"
        assert results[0].score == 0.92

    @pytest.mark.asyncio
    async def test_delete_by_file(self, store, mock_qdrant) -> None:
        """delete_by_file() should delete points matching file_path."""
        await store.delete_by_file("src/auth.py")
        mock_qdrant.delete.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/memory/tests/unit/test_semantic_store.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `packages/memory/src/semantic/store.py`:
```python
"""L3 Semantic Store — Qdrant vector search over codebase."""

from __future__ import annotations

import logging
from uuid import UUID

from qdrant_client import models
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    SparseVector,
    VectorParams,
)

from packages.memory.src.semantic.models import CodeChunk, SearchResult

logger = logging.getLogger(__name__)


class SemanticStore:
    """Qdrant-backed semantic search over team codebase.

    Uses named vectors (code, docstring) + sparse vectors (keywords).
    INT8 quantization keeps 100k LOC index under 100MB RAM.
    """

    def __init__(
        self,
        qdrant: object,
        embedder: object,
        team_id: UUID,
    ) -> None:
        self._qdrant = qdrant
        self._embedder = embedder
        self._team_id = team_id

    @property
    def collection_name(self) -> str:
        return f"code_search_{self._team_id}"

    async def ensure_collection(self) -> None:
        """Create Qdrant collection if it doesn't exist."""
        exists = await self._qdrant.collection_exists(self.collection_name)  # type: ignore[union-attr]
        if exists:
            return

        await self._qdrant.create_collection(  # type: ignore[union-attr]
            collection_name=self.collection_name,
            vectors_config={
                "code": VectorParams(size=384, distance=Distance.COSINE),
                "docstring": VectorParams(size=384, distance=Distance.COSINE),
            },
            quantization_config=ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,
                ),
            ),
        )
        logger.info("Created Qdrant collection: %s", self.collection_name)

    async def upsert(self, chunks: list[CodeChunk]) -> None:
        """Upsert code chunks with embeddings into Qdrant."""
        if not chunks:
            return

        # Batch embed code content
        contents = [c.content for c in chunks]
        embeddings = await self._embedder.embed_bulk(contents)  # type: ignore[union-attr]

        points = []
        for chunk, embedding in zip(chunks, embeddings):
            payload = {
                "file_path": chunk.file_path,
                "language": chunk.language,
                "module_name": chunk.module_name,
                "symbol_name": chunk.symbol_name,
                "symbol_type": chunk.symbol_type,
                "content": chunk.content,
                "line_start": chunk.line_start,
                "line_end": chunk.line_end,
                "dependencies": chunk.dependencies,
            }

            vectors = {"code": embedding}
            if chunk.docstring:
                # For docstrings, use same embedder (could be separate in future)
                ds_emb = await self._embedder.embed_query(chunk.docstring)  # type: ignore[union-attr]
                vectors["docstring"] = ds_emb

            points.append(
                PointStruct(
                    id=chunk.chunk_id,
                    vector=vectors,
                    payload=payload,
                )
            )

        await self._qdrant.upsert(  # type: ignore[union-attr]
            collection_name=self.collection_name,
            points=points,
        )
        logger.debug("Upserted %d chunks to %s", len(points), self.collection_name)

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        file_filter: str | None = None,
    ) -> list[SearchResult]:
        """Search for code chunks matching a natural language query."""
        query_embedding = await self._embedder.embed_query(query)  # type: ignore[union-attr]

        search_filter = None
        if file_filter:
            search_filter = Filter(
                must=[FieldCondition(key="file_path", match=MatchValue(value=file_filter))]
            )

        points = await self._qdrant.search(  # type: ignore[union-attr]
            collection_name=self.collection_name,
            query_vector=("code", query_embedding),
            limit=limit,
            query_filter=search_filter,
            with_payload=True,
        )

        results = []
        for point in points:
            payload = point.payload or {}
            chunk = CodeChunk(
                chunk_id=str(point.id),
                file_path=payload.get("file_path", ""),
                language=payload.get("language", ""),
                module_name=payload.get("module_name", ""),
                symbol_name=payload.get("symbol_name"),
                symbol_type=payload.get("symbol_type"),
                content=payload.get("content", ""),
                line_start=payload.get("line_start", 0),
                line_end=payload.get("line_end", 0),
                dependencies=payload.get("dependencies", []),
            )
            snippet = (
                f"{chunk.file_path}:{chunk.line_start}-{chunk.line_end}"
                f" {chunk.symbol_name or 'chunk'}"
            )
            results.append(
                SearchResult(
                    source="semantic",
                    score=point.score,
                    chunk=chunk,
                    snippet=snippet,
                )
            )

        return results

    async def delete_by_file(self, file_path: str) -> None:
        """Delete all points for a given file."""
        await self._qdrant.delete(  # type: ignore[union-attr]
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
                )
            ),
        )
        logger.debug("Deleted points for file: %s", file_path)

    async def delete_collection(self) -> None:
        """Delete the entire collection. Used at tournament end."""
        await self._qdrant.delete_collection(self.collection_name)  # type: ignore[union-attr]
        logger.info("Deleted Qdrant collection: %s", self.collection_name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/memory/tests/unit/test_semantic_store.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/memory/src/semantic/store.py packages/memory/tests/unit/test_semantic_store.py
git commit -m "feat(memory): implement L3 SemanticStore with Qdrant named vectors"
```

---

## Task 9: Hybrid Embedder (FastEmbed + LiteLLM)

**Files:**
- Create: `packages/memory/src/semantic/embedder.py`
- Test: `packages/memory/tests/unit/test_embedder.py`

- [ ] **Step 1: Write the failing test**

Create `packages/memory/tests/unit/test_embedder.py`:
```python
"""Tests for HybridEmbedder (FastEmbed + LiteLLM)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from packages.memory.src.semantic.embedder import HybridEmbedder


@pytest.fixture()
def mock_fastembed():
    """Mock FastEmbed TextEmbedding."""
    fe = MagicMock()
    fe.embed = MagicMock(return_value=iter([[0.1] * 384, [0.2] * 384]))
    return fe


@pytest.fixture()
def embedder(mock_fastembed) -> HybridEmbedder:
    return HybridEmbedder(fastembed_model=mock_fastembed, llm_client=None)


class TestHybridEmbedder:
    """Tests for the hybrid embedding strategy."""

    @pytest.mark.asyncio
    async def test_embed_bulk_uses_fastembed(self, embedder, mock_fastembed) -> None:
        """embed_bulk() should use FastEmbed for batch indexing."""
        results = await embedder.embed_bulk(["code 1", "code 2"])
        assert len(results) == 2
        assert len(results[0]) == 384
        mock_fastembed.embed.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_query_without_llm_falls_back_to_fastembed(
        self, embedder, mock_fastembed
    ) -> None:
        """embed_query() without LLM client should fall back to FastEmbed."""
        mock_fastembed.embed = MagicMock(return_value=iter([[0.5] * 384]))
        result = await embedder.embed_query("search query")
        assert len(result) == 384

    @pytest.mark.asyncio
    async def test_embed_query_with_llm_uses_llm(self, mock_fastembed) -> None:
        """embed_query() with LLM client should use LiteLLM for higher quality."""
        mock_llm = MagicMock()
        mock_llm.completion = AsyncMock(
            return_value=MagicMock(raw={"data": [{"embedding": [0.9] * 384}]})
        )
        embedder = HybridEmbedder(fastembed_model=mock_fastembed, llm_client=mock_llm)
        result = await embedder.embed_query("search query")
        assert len(result) == 384

    @pytest.mark.asyncio
    async def test_embed_bulk_empty_list(self, embedder) -> None:
        """embed_bulk() with empty list should return empty list."""
        results = await embedder.embed_bulk([])
        assert results == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/memory/tests/unit/test_embedder.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `packages/memory/src/semantic/embedder.py`:
```python
"""Hybrid Embedder — FastEmbed (local, free) for bulk + LiteLLM (proxy) for queries."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Default model: BAAI/bge-small-en-v1.5 (384-dim, ONNX, CPU)
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384


class HybridEmbedder:
    """FastEmbed for bulk indexing (free, local). LiteLLM for queries (higher quality).

    If LiteLLM is unavailable, queries also fall back to FastEmbed.
    """

    def __init__(
        self,
        fastembed_model: Any = None,
        llm_client: Any = None,
    ) -> None:
        self._fastembed = fastembed_model
        self._llm_client = llm_client

    @classmethod
    def create(cls, llm_client: Any = None) -> HybridEmbedder:
        """Factory that initializes FastEmbed with the default model."""
        from fastembed import TextEmbedding

        fe = TextEmbedding(model_name=DEFAULT_MODEL)
        return cls(fastembed_model=fe, llm_client=llm_client)

    async def embed_bulk(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using FastEmbed (local, free).

        Used for indexing code chunks — high throughput, zero API cost.
        """
        if not texts:
            return []
        embeddings = list(self._fastembed.embed(texts))
        return [list(e) for e in embeddings]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query.

        Uses LiteLLM if available (higher quality for search).
        Falls back to FastEmbed if LiteLLM is not configured.
        """
        if self._llm_client is not None:
            try:
                response = await self._llm_client.completion(
                    messages=[],
                    model="text-embedding-3-small",
                    max_tokens=1,
                )
                # Extract embedding from raw response
                data = response.raw.get("data", [{}])
                if data and "embedding" in data[0]:
                    return data[0]["embedding"][:EMBEDDING_DIM]
            except Exception:
                logger.warning("LiteLLM embedding failed, falling back to FastEmbed")

        # Fallback: use FastEmbed for query too
        embeddings = list(self._fastembed.embed([text]))
        return list(embeddings[0])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/memory/tests/unit/test_embedder.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/memory/src/semantic/embedder.py packages/memory/tests/unit/test_embedder.py
git commit -m "feat(memory): implement HybridEmbedder with FastEmbed bulk + LiteLLM query"
```

---

## Task 10: Grammar Loader (tree-sitter)

**Files:**
- Create: `packages/memory/src/indexer/grammars.py`
- Test: `packages/memory/tests/unit/test_grammars.py`

- [ ] **Step 1: Write the failing test**

Create `packages/memory/tests/unit/test_grammars.py`:
```python
"""Tests for GrammarLoader (lazy tree-sitter grammar loading)."""

from __future__ import annotations

import pytest

from packages.memory.src.indexer.grammars import GrammarLoader


class TestGrammarLoader:
    """Tests for lazy grammar loading."""

    def test_extension_to_language_mapping(self) -> None:
        """Common extensions should map to languages."""
        loader = GrammarLoader()
        assert loader.language_for_extension(".py") == "python"
        assert loader.language_for_extension(".ts") == "typescript"
        assert loader.language_for_extension(".tsx") == "typescript"
        assert loader.language_for_extension(".js") == "javascript"
        assert loader.language_for_extension(".jsx") == "javascript"

    def test_unknown_extension_returns_none(self) -> None:
        """Unknown extensions should return None."""
        loader = GrammarLoader()
        assert loader.language_for_extension(".xyz") is None
        assert loader.language_for_extension(".csv") is None

    def test_supported_extensions(self) -> None:
        """Should list all supported extensions."""
        loader = GrammarLoader()
        exts = loader.supported_extensions()
        assert ".py" in exts
        assert ".ts" in exts
        assert ".js" in exts
        assert ".md" in exts

    def test_get_parser_returns_parser(self) -> None:
        """get_parser() should return a tree-sitter Parser for known language."""
        loader = GrammarLoader()
        parser = loader.get_parser("python")
        assert parser is not None

    def test_get_parser_caches(self) -> None:
        """get_parser() should cache parsers after first load."""
        loader = GrammarLoader()
        p1 = loader.get_parser("python")
        p2 = loader.get_parser("python")
        assert p1 is p2

    def test_get_parser_unknown_returns_none(self) -> None:
        """get_parser() for unknown language should return None."""
        loader = GrammarLoader()
        assert loader.get_parser("cobol") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/memory/tests/unit/test_grammars.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `packages/memory/src/indexer/grammars.py`:
```python
"""Grammar Loader — Lazy-load tree-sitter grammars per language."""

from __future__ import annotations

import logging

import tree_sitter

logger = logging.getLogger(__name__)

# Extension → language mapping
EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".md": "markdown",
}

# Language → tree-sitter grammar module import path
GRAMMAR_MODULES: dict[str, str] = {
    "python": "tree_sitter_python",
    "javascript": "tree_sitter_javascript",
    "typescript": "tree_sitter_typescript.tsx",
}


class GrammarLoader:
    """Lazy-loads and caches tree-sitter grammars per language.

    Only loads the grammar for a language when first requested.
    Cached after first use — no repeated imports.
    """

    def __init__(self) -> None:
        self._parsers: dict[str, tree_sitter.Parser] = {}

    def language_for_extension(self, ext: str) -> str | None:
        """Map file extension to language name. Returns None if unsupported."""
        return EXTENSION_MAP.get(ext)

    def supported_extensions(self) -> set[str]:
        """Return all supported file extensions."""
        return set(EXTENSION_MAP.keys())

    def get_parser(self, language: str) -> tree_sitter.Parser | None:
        """Get or create a tree-sitter Parser for a language.

        Returns None if the grammar is not available.
        """
        if language in self._parsers:
            return self._parsers[language]

        module_path = GRAMMAR_MODULES.get(language)
        if module_path is None:
            # Markdown and others don't need tree-sitter parsing
            if language == "markdown":
                return None
            logger.debug("No grammar module for language: %s", language)
            return None

        try:
            import importlib

            mod = importlib.import_module(module_path)
            lang = tree_sitter.Language(mod.language())
            parser = tree_sitter.Parser(lang)
            self._parsers[language] = parser
            logger.info("Loaded tree-sitter grammar: %s", language)
            return parser
        except Exception:
            logger.warning("Failed to load tree-sitter grammar: %s", language, exc_info=True)
            return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/memory/tests/unit/test_grammars.py -v`
Expected: All 6 tests PASS (test_get_parser_returns_parser may need tree-sitter-python installed)

- [ ] **Step 5: Commit**

```bash
git add packages/memory/src/indexer/grammars.py packages/memory/tests/unit/test_grammars.py
git commit -m "feat(memory): implement GrammarLoader with lazy tree-sitter loading"
```

---

## Task 11: Code Parser (tree-sitter AST chunking)

**Files:**
- Create: `packages/memory/src/indexer/parser.py`
- Test: `packages/memory/tests/unit/test_parser.py`

- [ ] **Step 1: Write the failing test**

Create `packages/memory/tests/unit/test_parser.py`:
```python
"""Tests for CodeParser (tree-sitter AST chunking)."""

from __future__ import annotations

import pytest

from packages.memory.src.indexer.grammars import GrammarLoader
from packages.memory.src.indexer.parser import CodeParser
from packages.memory.src.semantic.models import CodeChunk


@pytest.fixture()
def parser() -> CodeParser:
    return CodeParser(grammar_loader=GrammarLoader())


SAMPLE_PYTHON = '''"""Auth module."""

def login(username: str, password: str) -> str:
    """Authenticate a user and return a token."""
    if not username:
        raise ValueError("Username required")
    return "token-123"


class AuthService:
    """Manages authentication."""

    def __init__(self, db):
        self.db = db

    def verify(self, token: str) -> bool:
        """Verify a JWT token."""
        return token.startswith("token-")
'''

SAMPLE_SHORT = '''"""Short module."""

x = 42
'''


class TestCodeParser:
    """Tests for tree-sitter code parsing."""

    def test_parse_python_functions(self, parser) -> None:
        """Should extract function and class chunks from Python."""
        chunks = parser.parse(
            content=SAMPLE_PYTHON,
            file_path="src/auth.py",
            language="python",
            module_name="auth",
        )
        names = [c.symbol_name for c in chunks]
        assert "login" in names
        assert "AuthService" in names

    def test_chunk_has_correct_metadata(self, parser) -> None:
        """Chunks should have file_path, language, module_name."""
        chunks = parser.parse(
            content=SAMPLE_PYTHON,
            file_path="src/auth.py",
            language="python",
            module_name="auth",
        )
        for chunk in chunks:
            assert chunk.file_path == "src/auth.py"
            assert chunk.language == "python"
            assert chunk.module_name == "auth"

    def test_short_file_single_chunk(self, parser) -> None:
        """Files < 50 lines should produce a single whole-file chunk."""
        chunks = parser.parse(
            content=SAMPLE_SHORT,
            file_path="src/constants.py",
            language="python",
            module_name="constants",
        )
        assert len(chunks) == 1
        assert chunks[0].symbol_type == "module"

    def test_chunk_id_format(self, parser) -> None:
        """chunk_id should be file_path::symbol_name."""
        chunks = parser.parse(
            content=SAMPLE_PYTHON,
            file_path="src/auth.py",
            language="python",
            module_name="auth",
        )
        for chunk in chunks:
            assert chunk.chunk_id.startswith("src/auth.py::")

    def test_docstrings_extracted(self, parser) -> None:
        """Functions with docstrings should have docstring field set."""
        chunks = parser.parse(
            content=SAMPLE_PYTHON,
            file_path="src/auth.py",
            language="python",
            module_name="auth",
        )
        login_chunk = next(c for c in chunks if c.symbol_name == "login")
        assert login_chunk.docstring is not None
        assert "Authenticate" in login_chunk.docstring

    def test_unsupported_language_returns_single_chunk(self, parser) -> None:
        """Unsupported language should return whole-file chunk."""
        chunks = parser.parse(
            content="some content",
            file_path="data.csv",
            language="csv",
            module_name="data",
        )
        assert len(chunks) == 1
        assert chunks[0].symbol_type == "module"

    def test_markdown_returns_section_chunks(self, parser) -> None:
        """Markdown files should be split by ## headings."""
        md = "# Title\n\n## Section A\nContent A.\n\n## Section B\nContent B.\n"
        chunks = parser.parse(
            content=md,
            file_path="docs/README.md",
            language="markdown",
            module_name="docs",
        )
        assert len(chunks) >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/memory/tests/unit/test_parser.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `packages/memory/src/indexer/parser.py`:
```python
"""Code Parser — Extract semantic chunks from source files via tree-sitter."""

from __future__ import annotations

import logging
import re

from packages.memory.src.indexer.grammars import GrammarLoader
from packages.memory.src.semantic.models import CodeChunk

logger = logging.getLogger(__name__)

# tree-sitter node types to extract per language
SYMBOL_NODE_TYPES: dict[str, set[str]] = {
    "python": {"function_definition", "class_definition"},
    "javascript": {"function_declaration", "class_declaration", "arrow_function", "export_statement"},
    "typescript": {"function_declaration", "class_declaration", "arrow_function", "export_statement"},
}

# Lines threshold: files shorter than this get a single chunk
SHORT_FILE_LINES = 50
# Sliding window for large files with no symbols
WINDOW_SIZE = 100
WINDOW_OVERLAP = 20


class CodeParser:
    """Extracts semantic code chunks from source files.

    Chunking strategy:
      - Files < 50 lines: single chunk (whole file)
      - Supported languages: extract function/class definitions via tree-sitter
      - Markdown: split by ## headings
      - Unsupported / no symbols: whole-file chunk (or sliding windows if > 500 lines)
    """

    def __init__(self, grammar_loader: GrammarLoader) -> None:
        self._grammars = grammar_loader

    def parse(
        self,
        *,
        content: str,
        file_path: str,
        language: str,
        module_name: str,
    ) -> list[CodeChunk]:
        """Parse a source file into semantic chunks."""
        lines = content.split("\n")
        line_count = len(lines)

        # Short files → single chunk
        if line_count < SHORT_FILE_LINES:
            return [self._whole_file_chunk(content, file_path, language, module_name)]

        # Markdown → heading-based splits
        if language == "markdown":
            return self._parse_markdown(content, file_path, module_name)

        # Try tree-sitter for supported languages
        parser = self._grammars.get_parser(language)
        if parser is not None:
            chunks = self._parse_with_treesitter(
                parser, content, file_path, language, module_name
            )
            if chunks:
                return chunks

        # Fallback: whole-file chunk
        return [self._whole_file_chunk(content, file_path, language, module_name)]

    def _whole_file_chunk(
        self, content: str, file_path: str, language: str, module_name: str
    ) -> CodeChunk:
        """Create a single chunk for the entire file."""
        return CodeChunk(
            chunk_id=f"{file_path}::module",
            file_path=file_path,
            language=language,
            module_name=module_name,
            symbol_name=None,
            symbol_type="module",
            content=content,
            line_start=1,
            line_end=len(content.split("\n")),
        )

    def _parse_with_treesitter(
        self,
        parser: object,
        content: str,
        file_path: str,
        language: str,
        module_name: str,
    ) -> list[CodeChunk]:
        """Extract chunks using tree-sitter AST."""
        tree = parser.parse(content.encode())  # type: ignore[union-attr]
        node_types = SYMBOL_NODE_TYPES.get(language, set())
        chunks: list[CodeChunk] = []

        def visit(node: object) -> None:
            if node.type in node_types:  # type: ignore[union-attr]
                start_line = node.start_point[0] + 1  # type: ignore[union-attr]
                end_line = node.end_point[0] + 1  # type: ignore[union-attr]
                text = content.encode()[node.start_byte:node.end_byte].decode()  # type: ignore[union-attr]

                symbol_name = self._extract_name(node, language)
                symbol_type = self._node_type_to_symbol_type(node.type)  # type: ignore[union-attr]
                docstring = self._extract_docstring(node, language, content)

                chunks.append(
                    CodeChunk(
                        chunk_id=f"{file_path}::{symbol_name or f'chunk_{start_line}'}",
                        file_path=file_path,
                        language=language,
                        module_name=module_name,
                        symbol_name=symbol_name,
                        symbol_type=symbol_type,
                        content=text,
                        docstring=docstring,
                        line_start=start_line,
                        line_end=end_line,
                    )
                )

            for child in node.children:  # type: ignore[union-attr]
                visit(child)

        visit(tree.root_node)
        return chunks

    def _extract_name(self, node: object, language: str) -> str | None:
        """Extract the name identifier from a definition node."""
        for child in node.children:  # type: ignore[union-attr]
            if child.type == "identifier":  # type: ignore[union-attr]
                return child.text.decode()  # type: ignore[union-attr]
            if child.type == "name":  # type: ignore[union-attr]
                return child.text.decode()  # type: ignore[union-attr]
        return None

    def _node_type_to_symbol_type(self, node_type: str) -> str:
        """Map tree-sitter node type to our symbol_type enum."""
        if "class" in node_type:
            return "class"
        if "function" in node_type or "arrow" in node_type:
            return "function"
        if "export" in node_type:
            return "function"  # Treat exports as functions for now
        return "function"

    def _extract_docstring(
        self, node: object, language: str, content: str
    ) -> str | None:
        """Extract docstring from a Python function/class."""
        if language != "python":
            return None
        # First child of body that is an expression_statement containing a string
        for child in node.children:  # type: ignore[union-attr]
            if child.type == "block":  # type: ignore[union-attr]
                for stmt in child.children:  # type: ignore[union-attr]
                    if stmt.type == "expression_statement":  # type: ignore[union-attr]
                        for expr in stmt.children:  # type: ignore[union-attr]
                            if expr.type == "string":  # type: ignore[union-attr]
                                raw = expr.text.decode()  # type: ignore[union-attr]
                                return raw.strip('"""').strip("'''").strip()
                        break
                break
        return None

    def _parse_markdown(
        self, content: str, file_path: str, module_name: str
    ) -> list[CodeChunk]:
        """Split markdown by ## headings."""
        sections: list[CodeChunk] = []
        current_heading: str | None = None
        current_lines: list[str] = []
        current_start = 1

        for i, line in enumerate(content.split("\n"), start=1):
            if line.startswith("## "):
                # Save previous section
                if current_lines:
                    section_content = "\n".join(current_lines)
                    name = current_heading or "intro"
                    sections.append(
                        CodeChunk(
                            chunk_id=f"{file_path}::{name}",
                            file_path=file_path,
                            language="markdown",
                            module_name=module_name,
                            symbol_name=name,
                            symbol_type="section",
                            content=section_content,
                            line_start=current_start,
                            line_end=i - 1,
                        )
                    )
                current_heading = line[3:].strip()
                current_lines = [line]
                current_start = i
            else:
                current_lines.append(line)

        # Last section
        if current_lines:
            name = current_heading or "intro"
            sections.append(
                CodeChunk(
                    chunk_id=f"{file_path}::{name}",
                    file_path=file_path,
                    language="markdown",
                    module_name=module_name,
                    symbol_name=name,
                    symbol_type="section",
                    content="\n".join(current_lines),
                    line_start=current_start,
                    line_end=current_start + len(current_lines) - 1,
                )
            )

        return sections if sections else [self._whole_file_chunk(content, file_path, "markdown", module_name)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/memory/tests/unit/test_parser.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/memory/src/indexer/parser.py packages/memory/tests/unit/test_parser.py
git commit -m "feat(memory): implement CodeParser with tree-sitter AST chunking"
```

---

## Task 12: Memory Promoter (Deterministic L1 -> L2)

**Files:**
- Create: `packages/memory/src/compression/promoter.py`
- Test: `packages/memory/tests/unit/test_promoter.py`

- [ ] **Step 1: Write the failing test**

Create `packages/memory/tests/unit/test_promoter.py`:
```python
"""Tests for MemoryPromoter (deterministic L1 -> L2 promotion)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from packages.memory.src.compression.promoter import MemoryPromoter
from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.working.models import WorkingState
from packages.shared.src.types.models import AgentRole, TournamentPhase


@pytest.fixture()
def promoter() -> MemoryPromoter:
    return MemoryPromoter()


@pytest.fixture()
def team_id():
    return uuid4()


@pytest.fixture()
def tournament_id():
    return uuid4()


class TestMemoryPromoter:
    """Tests for keyword-based promotion rules."""

    def test_adr_keyword_promotes(self, promoter, team_id, tournament_id) -> None:
        """Decisions with architecture keywords should promote as ADR."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=team_id,
            role=AgentRole.ARCHITECT,
            current_phase=TournamentPhase.ARCHITECTURE,
            recent_decisions=["Chose FastAPI over Flask for the REST API architecture"],
        )
        records = promoter.promote(state, tournament_id=tournament_id)
        adr_records = [r for r in records if r.record_type == RecordType.ADR]
        assert len(adr_records) >= 1

    def test_gotcha_keyword_promotes(self, promoter, team_id, tournament_id) -> None:
        """Decisions with gotcha keywords should promote as GOTCHA."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=team_id,
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            recent_decisions=["Careful: Redis drops idle connections, never forget retry wrapper"],
        )
        records = promoter.promote(state, tournament_id=tournament_id)
        gotcha_records = [r for r in records if r.record_type == RecordType.GOTCHA]
        assert len(gotcha_records) >= 1

    def test_coding_pattern_promotes(self, promoter, team_id, tournament_id) -> None:
        """Decisions with pattern keywords should promote as CODING_PATTERN."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=team_id,
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            recent_decisions=["Must use Depends() pattern for all FastAPI injection"],
        )
        records = promoter.promote(state, tournament_id=tournament_id)
        pattern_records = [r for r in records if r.record_type == RecordType.CODING_PATTERN]
        assert len(pattern_records) >= 1

    def test_tech_debt_promotes(self, promoter, team_id, tournament_id) -> None:
        """Decisions with bug/workaround keywords should promote as TECH_DEBT."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=team_id,
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            recent_decisions=["Bug: the ORM doesn't handle UUIDs, used a workaround"],
        )
        records = promoter.promote(state, tournament_id=tournament_id)
        debt_records = [r for r in records if r.record_type == RecordType.TECH_DEBT]
        assert len(debt_records) >= 1

    def test_no_promotion_for_routine(self, promoter, team_id, tournament_id) -> None:
        """Routine decisions should not be promoted."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=team_id,
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            recent_decisions=["Created file src/main.py", "Ran pytest"],
        )
        records = promoter.promote(state, tournament_id=tournament_id)
        assert len(records) == 0

    def test_frequent_files_promote_as_file_meta(
        self, promoter, team_id, tournament_id
    ) -> None:
        """Files touched > 3 times should promote as FILE_META."""
        state = WorkingState(
            agent_id=uuid4(),
            team_id=team_id,
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            recent_files_touched=[
                "src/api/auth.py",
                "src/api/auth.py",
                "src/api/auth.py",
                "src/api/auth.py",
                "src/models/user.py",
            ],
        )
        records = promoter.promote(state, tournament_id=tournament_id)
        file_records = [r for r in records if r.record_type == RecordType.FILE_META]
        assert len(file_records) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/memory/tests/unit/test_promoter.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `packages/memory/src/compression/promoter.py`:
```python
"""Memory Promoter — Deterministic L1 -> L2 keyword-based promotion."""

from __future__ import annotations

import re
from collections import Counter
from uuid import UUID

from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.working.models import WorkingState

# Keyword patterns per record type (case-insensitive)
PROMOTION_RULES: list[tuple[RecordType, re.Pattern[str]]] = [
    (RecordType.ADR, re.compile(r"\b(chose|decided|architecture|design|picked|selected)\b", re.I)),
    (RecordType.TECH_DEBT, re.compile(r"\b(bug|fix|workaround|hack|TODO|FIXME|shortcut)\b", re.I)),
    (RecordType.GOTCHA, re.compile(r"\b(gotcha|careful|don'?t|never|always|footgun|breaks|beware)\b", re.I)),
    (RecordType.CODING_PATTERN, re.compile(r"\b(pattern|convention|must use|should use|prefer|standard)\b", re.I)),
    (RecordType.AGENT_LEARNING, re.compile(r"\b(learned|discovered|realized|turns out|insight|found that)\b", re.I)),
    (RecordType.HOOK_DISCOVERY, re.compile(r"\b(formatter|linter|hook|auto-format|pre-commit|ruff|eslint)\b", re.I)),
]

# Files touched more than this many times get promoted as FILE_META
FILE_FREQUENCY_THRESHOLD = 3


class MemoryPromoter:
    """Promotes important L1 items to L2 records using deterministic keyword matching.

    No LLM calls. Pure Python logic.
    """

    def promote(
        self,
        state: WorkingState,
        *,
        tournament_id: UUID,
    ) -> list[ModuleRecord]:
        """Scan working state and create L2 records for promotable items.

        Returns list of new ModuleRecord instances (not yet persisted).
        """
        records: list[ModuleRecord] = []

        # Promote decisions by keyword
        for decision in state.recent_decisions:
            record_type = self._classify_decision(decision)
            if record_type is not None:
                records.append(
                    ModuleRecord(
                        team_id=state.team_id,
                        tournament_id=tournament_id,
                        record_type=record_type,
                        module_name=self._infer_module(state),
                        title=decision[:200],
                        content=decision,
                        agent_id=state.agent_id,
                        agent_role=state.role,
                    )
                )

        # Promote frequently-touched files
        file_counts = Counter(state.recent_files_touched)
        for file_path, count in file_counts.items():
            if count > FILE_FREQUENCY_THRESHOLD:
                records.append(
                    ModuleRecord(
                        team_id=state.team_id,
                        tournament_id=tournament_id,
                        record_type=RecordType.FILE_META,
                        module_name=self._module_from_path(file_path),
                        file_path=file_path,
                        title=f"Frequently modified: {file_path}",
                        content=f"Modified {count} times during this sprint.",
                        agent_id=state.agent_id,
                        agent_role=state.role,
                    )
                )

        return records

    def _classify_decision(self, text: str) -> RecordType | None:
        """Classify a decision string into a RecordType using keyword matching."""
        for record_type, pattern in PROMOTION_RULES:
            if pattern.search(text):
                return record_type
        return None

    def _infer_module(self, state: WorkingState) -> str:
        """Infer module name from current file or task."""
        if state.current_file:
            return self._module_from_path(state.current_file)
        if state.current_task:
            return "general"
        return "unknown"

    def _module_from_path(self, path: str) -> str:
        """Extract module name from a file path."""
        parts = path.replace("\\", "/").split("/")
        # Try to find the first meaningful directory after src/
        for i, part in enumerate(parts):
            if part == "src" and i + 1 < len(parts):
                return parts[i + 1].replace(".py", "").replace(".ts", "")
        # Fallback: second-to-last path component
        if len(parts) >= 2:
            return parts[-2]
        return parts[0] if parts else "unknown"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/memory/tests/unit/test_promoter.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/memory/src/compression/promoter.py packages/memory/tests/unit/test_promoter.py
git commit -m "feat(memory): implement MemoryPromoter with keyword-based L1->L2 promotion"
```

---

## Task 13: Context Compressor (Haiku Summarization)

**Files:**
- Create: `packages/memory/src/compression/compressor.py`
- Test: `packages/memory/tests/unit/test_compressor.py`

- [ ] **Step 1: Write the failing test**

Create `packages/memory/tests/unit/test_compressor.py`:
```python
"""Tests for ContextCompressor (Haiku 4.5 summarization)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from packages.memory.src.compression.compressor import CompressedContext, ContextCompressor
from packages.memory.src.working.models import WorkingState
from packages.shared.src.types.models import AgentRole, TournamentPhase


@pytest.fixture()
def mock_llm():
    """Mock LLM client returning a summary."""
    client = MagicMock()
    client.completion = AsyncMock(
        return_value=MagicMock(
            content="Agent built auth module with bcrypt. Pending: rate limiting.",
            usage=MagicMock(total_tokens=200, cost_usd=0.001),
        )
    )
    return client


@pytest.fixture()
def compressor(mock_llm) -> ContextCompressor:
    return ContextCompressor(llm_client=mock_llm)


@pytest.fixture()
def big_state() -> WorkingState:
    return WorkingState(
        agent_id=uuid4(),
        team_id=uuid4(),
        role=AgentRole.BUILDER,
        current_phase=TournamentPhase.BUILD,
        current_task="Build auth module",
        recent_decisions=[f"Decision {i}: detailed reasoning about choice {i}" for i in range(10)],
        recent_files_touched=[f"src/file_{i}.py" for i in range(20)],
        active_errors=["Error: connection refused"],
        context_summary="Previous context about the project setup.",
    )


class TestContextCompressor:
    """Tests for Haiku-based context compression."""

    @pytest.mark.asyncio
    async def test_compress_returns_compressed_context(
        self, compressor, big_state
    ) -> None:
        """compress() should return a CompressedContext."""
        result = await compressor.compress(big_state)
        assert isinstance(result, CompressedContext)
        assert len(result.summary) > 0

    @pytest.mark.asyncio
    async def test_compress_preserves_top_3_decisions(
        self, compressor, big_state
    ) -> None:
        """compress() should preserve the 3 most recent decisions."""
        result = await compressor.compress(big_state)
        assert len(result.preserved_decisions) == 3

    @pytest.mark.asyncio
    async def test_compress_reports_dropped_count(
        self, compressor, big_state
    ) -> None:
        """compress() should report how many items were dropped."""
        result = await compressor.compress(big_state)
        assert result.dropped_count > 0

    @pytest.mark.asyncio
    async def test_compress_calls_llm_with_haiku(self, compressor, mock_llm, big_state) -> None:
        """compress() should call LLM with claude-haiku-4-5 model."""
        await compressor.compress(big_state)
        call_kwargs = mock_llm.completion.call_args
        assert call_kwargs.kwargs["model"] == "claude-haiku-4-5"

    @pytest.mark.asyncio
    async def test_apply_compressed_updates_state(self, compressor, big_state) -> None:
        """apply() should update the working state with compressed data."""
        compressed = CompressedContext(
            summary="Compressed summary of work.",
            preserved_decisions=["Decision 9", "Decision 8", "Decision 7"],
            dropped_count=7,
        )
        updated = compressor.apply(big_state, compressed)
        assert updated.context_summary == "Compressed summary of work."
        assert len(updated.recent_decisions) == 3
        assert len(updated.recent_files_touched) == 10  # Trimmed to last 10
        assert len(updated.active_errors) == 1  # Errors never compressed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/memory/tests/unit/test_compressor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `packages/memory/src/compression/compressor.py`:
```python
"""Context Compressor — Haiku 4.5 summarization for L1 overflow."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from packages.memory.src.working.models import WorkingState

logger = logging.getLogger(__name__)

COMPRESSION_MODEL = "claude-haiku-4-5"

COMPRESSION_PROMPT = """Summarize this agent's working state into a dense paragraph.
Preserve: current task, key decisions, unresolved errors, files modified.
Drop: routine actions, redundant info, resolved issues.

Working state:
{state_text}

Write a concise summary (max 500 tokens):"""


@dataclass
class CompressedContext:
    """Result of compressing an agent's working state."""

    summary: str
    preserved_decisions: list[str]
    dropped_count: int


class ContextCompressor:
    """Calls Haiku 4.5 to compress L1 working state when it exceeds token threshold.

    Cost: ~$0.001 per compression. Latency: ~500ms.
    """

    def __init__(self, llm_client: Any) -> None:
        self._llm = llm_client

    async def compress(self, state: WorkingState) -> CompressedContext:
        """Compress a working state into a summary + preserved top decisions."""
        state_text = state.model_dump_json(indent=2)

        response = await self._llm.completion(
            messages=[
                {"role": "user", "content": COMPRESSION_PROMPT.format(state_text=state_text)},
            ],
            model=COMPRESSION_MODEL,
            temperature=0.1,
            max_tokens=600,
            trace_name="memory.compress",
            trace_metadata={
                "agent_id": str(state.agent_id),
                "role": state.role.value,
            },
        )

        # Preserve the 3 most recent decisions verbatim
        preserved = state.recent_decisions[-3:] if state.recent_decisions else []
        dropped = max(0, len(state.recent_decisions) - 3)

        return CompressedContext(
            summary=response.content,
            preserved_decisions=preserved,
            dropped_count=dropped,
        )

    def apply(self, state: WorkingState, compressed: CompressedContext) -> WorkingState:
        """Apply compression results to working state.

        - Replaces context_summary with new summary
        - Trims recent_decisions to preserved only
        - Trims recent_files_touched to last 10
        - Active errors are NEVER compressed
        """
        return state.model_copy(
            update={
                "context_summary": compressed.summary,
                "recent_decisions": compressed.preserved_decisions,
                "recent_files_touched": state.recent_files_touched[-10:],
                # active_errors unchanged
            }
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/memory/tests/unit/test_compressor.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/memory/src/compression/compressor.py packages/memory/tests/unit/test_compressor.py
git commit -m "feat(memory): implement ContextCompressor with Haiku 4.5 summarization"
```

---

## Task 14: Document Syncer (Self-Healing .md Files)

**Files:**
- Create: `packages/memory/src/compression/doc_sync.py`
- Test: `packages/memory/tests/unit/test_doc_sync.py`

- [ ] **Step 1: Write the failing test**

Create `packages/memory/tests/unit/test_doc_sync.py`:
```python
"""Tests for DocumentSyncer (L2 records -> .md files)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from packages.memory.src.compression.doc_sync import DocumentSyncer
from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.shared.src.types.models import AgentRole


@pytest.fixture()
def workspace(tmp_path) -> Path:
    """Create a temp workspace with .claude/ structure."""
    claude_dir = tmp_path / ".claude"
    (claude_dir / "rules").mkdir(parents=True)
    (claude_dir / "agents").mkdir(parents=True)
    (claude_dir / "memory").mkdir(parents=True)
    (claude_dir / "hooks").mkdir(parents=True)
    # Create initial files
    (tmp_path / "DECISIONS.md").write_text("# Architecture Decisions\n")
    (tmp_path / "TECH_DEBT.md").write_text("# Technical Debt\n")
    (claude_dir / "rules" / "gotchas.md").write_text("# Gotchas\n")
    (claude_dir / "rules" / "project-rules.md").write_text("# Project Rules\n")
    (claude_dir / "memory" / "decisions-log.md").write_text("# Decisions Log\n")
    (claude_dir / "memory" / "gotchas.md").write_text("# Gotchas\n")
    return tmp_path


@pytest.fixture()
def syncer(workspace) -> DocumentSyncer:
    return DocumentSyncer(workspace_path=str(workspace))


class TestDocumentSyncer:
    """Tests for routing records to .md files."""

    def test_sync_adr_appends_to_decisions_md(
        self, syncer, workspace, team_id, tournament_id
    ) -> None:
        """ADR records should append to DECISIONS.md."""
        record = ModuleRecord(
            team_id=team_id,
            tournament_id=tournament_id,
            record_type=RecordType.ADR,
            module_name="auth",
            title="Chose bcrypt over argon2",
            content="bcrypt — simpler API, well-supported.",
            agent_role=AgentRole.BUILDER,
        )
        syncer.sync([record])
        content = (workspace / "DECISIONS.md").read_text()
        assert "Chose bcrypt over argon2" in content

    def test_sync_adr_also_appends_to_memory_log(
        self, syncer, workspace, team_id, tournament_id
    ) -> None:
        """ADR should also go to .claude/memory/decisions-log.md."""
        record = ModuleRecord(
            team_id=team_id,
            tournament_id=tournament_id,
            record_type=RecordType.ADR,
            module_name="auth",
            title="Chose bcrypt",
            content="bcrypt for password hashing.",
        )
        syncer.sync([record])
        content = (workspace / ".claude" / "memory" / "decisions-log.md").read_text()
        assert "Chose bcrypt" in content

    def test_sync_gotcha_to_rules_and_memory(
        self, syncer, workspace, team_id, tournament_id
    ) -> None:
        """GOTCHA should go to .claude/rules/gotchas.md AND .claude/memory/gotchas.md."""
        record = ModuleRecord(
            team_id=team_id,
            tournament_id=tournament_id,
            record_type=RecordType.GOTCHA,
            module_name="cache",
            title="Redis drops idle connections",
            content="Wrap with retry. Symptom: ConnectionError after 5min idle.",
            agent_role=AgentRole.BUILDER,
        )
        syncer.sync([record])

        rules_content = (workspace / ".claude" / "rules" / "gotchas.md").read_text()
        assert "Redis drops idle connections" in rules_content

        memory_content = (workspace / ".claude" / "memory" / "gotchas.md").read_text()
        assert "Redis drops idle connections" in memory_content

    def test_sync_coding_pattern_to_project_rules(
        self, syncer, workspace, team_id, tournament_id
    ) -> None:
        """CODING_PATTERN should go to .claude/rules/project-rules.md."""
        record = ModuleRecord(
            team_id=team_id,
            tournament_id=tournament_id,
            record_type=RecordType.CODING_PATTERN,
            module_name="api",
            title="Use Depends() for all DI",
            content="Always use FastAPI Depends() for dependency injection.",
        )
        syncer.sync([record])
        content = (workspace / ".claude" / "rules" / "project-rules.md").read_text()
        assert "Depends()" in content

    def test_sync_tech_debt_to_tech_debt_md(
        self, syncer, workspace, team_id, tournament_id
    ) -> None:
        """TECH_DEBT should append to TECH_DEBT.md."""
        record = ModuleRecord(
            team_id=team_id,
            tournament_id=tournament_id,
            record_type=RecordType.TECH_DEBT,
            module_name="orm",
            title="UUID workaround in ORM",
            content="SQLAlchemy UUID handling has a bug, using string cast.",
        )
        syncer.sync([record])
        content = (workspace / "TECH_DEBT.md").read_text()
        assert "UUID workaround" in content

    def test_sync_skips_duplicate_titles(
        self, syncer, workspace, team_id, tournament_id
    ) -> None:
        """Should not append if the exact title already exists in the file."""
        record = ModuleRecord(
            team_id=team_id,
            tournament_id=tournament_id,
            record_type=RecordType.ADR,
            module_name="auth",
            title="Chose bcrypt",
            content="bcrypt for hashing.",
        )
        syncer.sync([record])
        syncer.sync([record])  # Second time
        content = (workspace / "DECISIONS.md").read_text()
        assert content.count("Chose bcrypt") == 1

    def test_sync_returns_synced_record_ids(
        self, syncer, workspace, team_id, tournament_id
    ) -> None:
        """sync() should return the IDs of records it processed."""
        record = ModuleRecord(
            team_id=team_id,
            tournament_id=tournament_id,
            record_type=RecordType.ADR,
            module_name="auth",
            title="Some ADR",
            content="Content.",
        )
        ids = syncer.sync([record])
        assert record.id in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/memory/tests/unit/test_doc_sync.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `packages/memory/src/compression/doc_sync.py`:
```python
"""Document Syncer — Route L2 records to project .md files."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from packages.memory.src.module.models import ModuleRecord, RecordType

logger = logging.getLogger(__name__)

# Routing table: RecordType -> list of relative file paths
ROUTING_TABLE: dict[RecordType, list[str]] = {
    RecordType.ADR: ["DECISIONS.md", ".claude/memory/decisions-log.md"],
    RecordType.TECH_DEBT: ["TECH_DEBT.md", ".claude/rules/gotchas.md", ".claude/memory/gotchas.md"],
    RecordType.GOTCHA: [".claude/rules/gotchas.md", ".claude/memory/gotchas.md"],
    RecordType.CODING_PATTERN: [".claude/rules/project-rules.md", ".claude/rules/stack-rules.md"],
    RecordType.AGENT_LEARNING: [".claude/agents/{role}-notes.md"],
    RecordType.HOOK_DISCOVERY: [".claude/hooks/{title}.sh"],
    RecordType.FILE_META: [],  # Only synced to CLAUDE.md via LLM (separate path)
    RecordType.DEPENDENCY: [],  # Only synced to ARCHITECTURE.md via LLM (separate path)
    RecordType.ACTION_LOG: [],  # Only synced to STATUS.md via LLM (separate path)
    RecordType.SIGNATURE: [],  # Not synced to docs
}


class DocumentSyncer:
    """Routes L2 ModuleRecords to the appropriate project .md files.

    Deterministic appends for most types. Deduplicates by title.
    LLM-based regeneration (STATUS.md, ARCHITECTURE.md, CLAUDE.md) is
    handled separately via explicit method calls, not routing table.
    """

    def __init__(self, workspace_path: str) -> None:
        self._workspace = Path(workspace_path)

    def sync(self, records: list[ModuleRecord]) -> list[UUID]:
        """Sync a batch of records to their target .md files.

        Returns list of record IDs that were successfully synced.
        """
        synced_ids: list[UUID] = []

        for record in records:
            targets = ROUTING_TABLE.get(record.record_type, [])
            if not targets:
                continue

            for target_template in targets:
                target_path = self._resolve_path(target_template, record)
                if target_path is None:
                    continue

                # Ensure parent directory exists
                target_path.parent.mkdir(parents=True, exist_ok=True)

                # Read existing content for dedup
                existing = ""
                if target_path.exists():
                    existing = target_path.read_text()

                # Skip if title already present (dedup)
                if record.title in existing:
                    logger.debug("Skipping duplicate: %s in %s", record.title, target_path)
                    continue

                # Format and append
                entry = self._format_entry(record)
                with target_path.open("a") as f:
                    f.write(entry)

                logger.debug(
                    "Synced %s record '%s' to %s",
                    record.record_type.value,
                    record.title,
                    target_path,
                )

            synced_ids.append(record.id)

        return synced_ids

    def _resolve_path(self, template: str, record: ModuleRecord) -> Path | None:
        """Resolve a path template with record data."""
        try:
            resolved = template.format(
                role=record.agent_role.value if record.agent_role else "unknown",
                title=record.title.lower().replace(" ", "-")[:50],
            )
        except (KeyError, AttributeError):
            resolved = template
        return self._workspace / resolved

    def _format_entry(self, record: ModuleRecord) -> str:
        """Format a record as a markdown entry."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        agent_info = f" | **Agent:** {record.agent_role.value}" if record.agent_role else ""

        if record.record_type == RecordType.ADR:
            return (
                f"\n## ADR: {record.title}\n"
                f"**Date:** {now}{agent_info}\n"
                f"**Module:** {record.module_name}\n"
                f"{record.content}\n"
            )

        if record.record_type == RecordType.GOTCHA:
            return (
                f"\n## G: {record.title}\n"
                f"**Discovered:** {now}{agent_info}\n"
                f"{record.content}\n"
            )

        if record.record_type == RecordType.TECH_DEBT:
            return (
                f"\n## DEBT: {record.title}\n"
                f"**Date:** {now}{agent_info}\n"
                f"**Module:** {record.module_name}\n"
                f"{record.content}\n"
            )

        if record.record_type == RecordType.CODING_PATTERN:
            return (
                f"\n## Pattern: {record.title}\n"
                f"**Module:** {record.module_name}\n"
                f"{record.content}\n"
            )

        if record.record_type == RecordType.AGENT_LEARNING:
            return (
                f"\n## Learning: {record.title}\n"
                f"**Date:** {now}\n"
                f"{record.content}\n"
            )

        # Default format
        return f"\n## {record.title}\n{record.content}\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/memory/tests/unit/test_doc_sync.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/memory/src/compression/doc_sync.py packages/memory/tests/unit/test_doc_sync.py
git commit -m "feat(memory): implement DocumentSyncer with routing table for self-healing docs"
```

---

## Task 15: Indexing Pipeline (parse -> embed -> upsert)

**Files:**
- Create: `packages/memory/src/indexer/pipeline.py`
- Create: `packages/memory/src/indexer/watcher.py`
- Test: `packages/memory/tests/integration/test_indexer_pipeline.py`

- [ ] **Step 1: Write the failing test**

Create `packages/memory/tests/integration/test_indexer_pipeline.py`:
```python
"""Integration tests for IndexingPipeline (parse -> embed -> upsert)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from packages.memory.src.indexer.grammars import GrammarLoader
from packages.memory.src.indexer.parser import CodeParser
from packages.memory.src.indexer.pipeline import IndexingPipeline


@pytest.fixture()
def mock_semantic_store():
    store = MagicMock()
    store.upsert = AsyncMock()
    store.delete_by_file = AsyncMock()
    return store


@pytest.fixture()
def mock_module_store():
    store = MagicMock()
    store.insert_batch = AsyncMock()
    return store


@pytest.fixture()
def pipeline(mock_semantic_store, mock_module_store, team_id, tournament_id):
    grammar_loader = GrammarLoader()
    parser = CodeParser(grammar_loader=grammar_loader)
    mock_embedder = MagicMock()
    mock_embedder.embed_bulk = AsyncMock(return_value=[[0.1] * 384])
    return IndexingPipeline(
        parser=parser,
        embedder=mock_embedder,
        semantic_store=mock_semantic_store,
        module_store=mock_module_store,
        team_id=team_id,
        tournament_id=tournament_id,
    )


@pytest.fixture()
def workspace(tmp_path) -> Path:
    """Create a workspace with sample files."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text(
        'def login(user, pw):\n    """Login."""\n    return "ok"\n'
    )
    (tmp_path / "src" / "main.py").write_text('print("hello")\n')
    return tmp_path


class TestIndexingPipeline:
    """Integration tests for the indexing pipeline."""

    @pytest.mark.asyncio
    async def test_index_files_upserts_to_qdrant(
        self, pipeline, mock_semantic_store, workspace
    ) -> None:
        """index_files() should parse, embed, and upsert to Qdrant."""
        files = [str(workspace / "src" / "auth.py")]
        await pipeline.index_files(files)
        mock_semantic_store.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_files_creates_file_meta_records(
        self, pipeline, mock_module_store, workspace
    ) -> None:
        """index_files() should create FILE_META records in L2."""
        files = [str(workspace / "src" / "auth.py")]
        await pipeline.index_files(files)
        mock_module_store.insert_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_empty_list_is_noop(
        self, pipeline, mock_semantic_store
    ) -> None:
        """index_files([]) should not call upsert."""
        await pipeline.index_files([])
        mock_semantic_store.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_deleted_files(
        self, pipeline, mock_semantic_store
    ) -> None:
        """remove_files() should delete from Qdrant."""
        await pipeline.remove_files(["src/old_file.py"])
        mock_semantic_store.delete_by_file.assert_called_once_with("src/old_file.py")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/memory/tests/integration/test_indexer_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the pipeline**

Create `packages/memory/src/indexer/pipeline.py`:
```python
"""Indexing Pipeline — Parse -> embed -> upsert to Qdrant + L2 FILE_META."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from packages.memory.src.indexer.grammars import GrammarLoader
from packages.memory.src.indexer.parser import CodeParser
from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.semantic.models import CodeChunk

logger = logging.getLogger(__name__)


class IndexingPipeline:
    """Orchestrates: parse files -> embed chunks -> upsert to Qdrant + L2."""

    def __init__(
        self,
        parser: CodeParser,
        embedder: object,
        semantic_store: object,
        module_store: object,
        team_id: UUID,
        tournament_id: UUID,
    ) -> None:
        self._parser = parser
        self._embedder = embedder
        self._semantic_store = semantic_store
        self._module_store = module_store
        self._team_id = team_id
        self._tournament_id = tournament_id
        self._grammar_loader = parser._grammars

    async def index_files(self, file_paths: list[str]) -> int:
        """Index a batch of files. Returns number of chunks indexed."""
        if not file_paths:
            return 0

        all_chunks: list[CodeChunk] = []
        file_meta_records: list[ModuleRecord] = []

        for file_path in file_paths:
            try:
                path = Path(file_path)
                if not path.exists():
                    logger.warning("File not found: %s", file_path)
                    continue

                content = path.read_text(errors="replace")
                ext = path.suffix
                language = self._grammar_loader.language_for_extension(ext)
                if language is None:
                    continue

                module_name = self._infer_module(file_path)
                chunks = self._parser.parse(
                    content=content,
                    file_path=file_path,
                    language=language,
                    module_name=module_name,
                )
                all_chunks.extend(chunks)

                # Create FILE_META record for L2
                file_meta_records.append(
                    ModuleRecord(
                        team_id=self._team_id,
                        tournament_id=self._tournament_id,
                        record_type=RecordType.FILE_META,
                        module_name=module_name,
                        file_path=file_path,
                        title=f"File: {path.name}",
                        content=f"{len(chunks)} chunks, {len(content.splitlines())} lines, language={language}",
                    )
                )

            except Exception:
                logger.exception("Failed to index file: %s", file_path)

        if all_chunks:
            await self._semantic_store.upsert(all_chunks)  # type: ignore[union-attr]
        if file_meta_records:
            await self._module_store.insert_batch(file_meta_records)  # type: ignore[union-attr]

        logger.info("Indexed %d chunks from %d files", len(all_chunks), len(file_paths))
        return len(all_chunks)

    async def remove_files(self, file_paths: list[str]) -> None:
        """Remove indexed data for deleted files."""
        for file_path in file_paths:
            await self._semantic_store.delete_by_file(file_path)  # type: ignore[union-attr]

    def _infer_module(self, file_path: str) -> str:
        """Infer module name from file path."""
        parts = file_path.replace("\\", "/").split("/")
        for i, part in enumerate(parts):
            if part == "src" and i + 1 < len(parts):
                return parts[i + 1].replace(".py", "").replace(".ts", "")
        if len(parts) >= 2:
            return parts[-2]
        return "root"
```

- [ ] **Step 4: Write the watcher**

Create `packages/memory/src/indexer/watcher.py`:
```python
"""Codebase Watcher — Debounced 60s mtime-based file change detection."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from packages.memory.src.indexer.grammars import GrammarLoader

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 60
SUPPORTED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".md"}


class CodebaseWatcher:
    """Scans workspace for changed files every 60 seconds and triggers indexing.

    Uses mtime-based change detection. No filesystem watchers needed.
    Runs as an asyncio.Task per team.
    """

    def __init__(
        self,
        workspace_path: str,
        pipeline: object,
        debounce_seconds: int = DEBOUNCE_SECONDS,
    ) -> None:
        self._workspace = Path(workspace_path)
        self._pipeline = pipeline
        self._debounce = debounce_seconds
        self._last_mtimes: dict[str, float] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the watcher loop as a background task."""
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("CodebaseWatcher started for %s", self._workspace)

    async def stop(self) -> None:
        """Stop the watcher loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("CodebaseWatcher stopped for %s", self._workspace)

    async def _watch_loop(self) -> None:
        """Main loop: scan, detect changes, trigger indexing."""
        while self._running:
            try:
                changed, removed = self._scan_changes()
                if changed:
                    await self._pipeline.index_files(changed)  # type: ignore[union-attr]
                if removed:
                    await self._pipeline.remove_files(removed)  # type: ignore[union-attr]
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Watcher error")

            await asyncio.sleep(self._debounce)

    def _scan_changes(self) -> tuple[list[str], list[str]]:
        """Scan workspace for changed and removed files."""
        changed: list[str] = []
        current_files: set[str] = set()

        for root, _dirs, files in os.walk(self._workspace):
            # Skip hidden dirs and common non-code dirs
            root_path = Path(root)
            if any(p.startswith(".") for p in root_path.parts):
                continue
            if any(p in ("node_modules", "__pycache__", ".git", "venv") for p in root_path.parts):
                continue

            for fname in files:
                fpath = os.path.join(root, fname)
                ext = os.path.splitext(fname)[1]
                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                current_files.add(fpath)
                try:
                    mtime = os.path.getmtime(fpath)
                except OSError:
                    continue

                last_mtime = self._last_mtimes.get(fpath)
                if last_mtime is None or mtime > last_mtime:
                    changed.append(fpath)
                    self._last_mtimes[fpath] = mtime

        # Detect removed files
        previously_known = set(self._last_mtimes.keys())
        removed = list(previously_known - current_files)
        for r in removed:
            del self._last_mtimes[r]

        return changed, removed
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest packages/memory/tests/integration/test_indexer_pipeline.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add packages/memory/src/indexer/pipeline.py packages/memory/src/indexer/watcher.py packages/memory/tests/integration/test_indexer_pipeline.py
git commit -m "feat(memory): implement IndexingPipeline and CodebaseWatcher"
```

---

## Task 16: MemoryManager Facade

**Files:**
- Create: `packages/memory/src/manager.py`
- Test: `packages/memory/tests/integration/test_memory_manager.py`

- [ ] **Step 1: Write the failing test**

Create `packages/memory/tests/integration/test_memory_manager.py`:
```python
"""Integration tests for MemoryManager facade."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from packages.memory.src.manager import MemoryManager
from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.semantic.models import MemoryContext, SearchResult
from packages.memory.src.working.models import WorkingState
from packages.shared.src.types.models import AgentRole, TournamentPhase


@pytest.fixture()
def mock_working_store():
    store = MagicMock()
    store.save = AsyncMock()
    store.load = AsyncMock(
        return_value=WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            current_task="Build auth",
        )
    )
    store.delete = AsyncMock()
    store.exceeds_threshold = AsyncMock(return_value=False)
    return store


@pytest.fixture()
def mock_module_store():
    store = MagicMock()
    store.insert = AsyncMock()
    store.insert_batch = AsyncMock()
    store.get_by_type = AsyncMock(return_value=[])
    store.get_unsynced = AsyncMock(return_value=[])
    store.mark_synced = AsyncMock()
    store.search_fulltext = AsyncMock(return_value=[])
    return store


@pytest.fixture()
def mock_semantic_store():
    store = MagicMock()
    store.search = AsyncMock(return_value=[])
    store.ensure_collection = AsyncMock()
    return store


@pytest.fixture()
def mock_compressor():
    comp = MagicMock()
    comp.compress = AsyncMock()
    comp.apply = MagicMock()
    return comp


@pytest.fixture()
def mock_promoter():
    prom = MagicMock()
    prom.promote = MagicMock(return_value=[])
    return prom


@pytest.fixture()
def mock_doc_syncer():
    ds = MagicMock()
    ds.sync = MagicMock(return_value=[])
    return ds


@pytest.fixture()
def manager(
    mock_working_store,
    mock_module_store,
    mock_semantic_store,
    mock_compressor,
    mock_promoter,
    mock_doc_syncer,
    team_id,
    tournament_id,
):
    return MemoryManager(
        team_id=team_id,
        tournament_id=tournament_id,
        working_store=mock_working_store,
        module_store=mock_module_store,
        semantic_store=mock_semantic_store,
        compressor=mock_compressor,
        promoter=mock_promoter,
        doc_syncer=mock_doc_syncer,
    )


class TestMemoryManagerRecall:
    """Tests for MemoryManager.recall()."""

    @pytest.mark.asyncio
    async def test_recall_returns_memory_context(self, manager, agent_id) -> None:
        """recall() should return a MemoryContext with all 3 layers."""
        ctx = await manager.recall(agent_id, AgentRole.BUILDER, "auth login")
        assert isinstance(ctx, MemoryContext)
        assert ctx.working_state is not None

    @pytest.mark.asyncio
    async def test_recall_reads_all_3_layers(
        self, manager, mock_working_store, mock_module_store, mock_semantic_store, agent_id
    ) -> None:
        """recall() should query L1, L2, and L3."""
        await manager.recall(agent_id, AgentRole.BUILDER, "auth")
        mock_working_store.load.assert_called_once()
        mock_module_store.search_fulltext.assert_called_once()
        mock_semantic_store.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_recall_triggers_overflow_when_exceeded(
        self, manager, mock_working_store, mock_compressor, agent_id
    ) -> None:
        """recall() should trigger overflow handler when L1 exceeds threshold."""
        mock_working_store.exceeds_threshold = AsyncMock(return_value=True)
        mock_compressor.compress = AsyncMock(
            return_value=MagicMock(
                summary="compressed",
                preserved_decisions=[],
                dropped_count=5,
            )
        )
        mock_compressor.apply = MagicMock(
            return_value=WorkingState(
                agent_id=agent_id,
                team_id=manager._team_id,
                role=AgentRole.BUILDER,
                current_phase=TournamentPhase.BUILD,
                context_summary="compressed",
            )
        )
        await manager.recall(agent_id, AgentRole.BUILDER, "query")
        mock_compressor.compress.assert_called_once()


class TestMemoryManagerRecord:
    """Tests for MemoryManager.record()."""

    @pytest.mark.asyncio
    async def test_record_updates_l1(
        self, manager, mock_working_store, agent_id
    ) -> None:
        """record() should update working state in Redis."""
        await manager.record(
            agent_id,
            AgentRole.BUILDER,
            task="Build auth endpoints",
            file_touched="src/auth.py",
        )
        mock_working_store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_with_decision_updates_decisions(
        self, manager, mock_working_store, agent_id
    ) -> None:
        """record() with decision should append to recent_decisions."""
        await manager.record(
            agent_id,
            AgentRole.BUILDER,
            decision="Chose bcrypt for password hashing",
        )
        mock_working_store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_with_module_records_inserts_to_l2(
        self, manager, mock_module_store, agent_id, team_id, tournament_id
    ) -> None:
        """record() with module_records should insert to L2."""
        records = [
            ModuleRecord(
                team_id=team_id,
                tournament_id=tournament_id,
                record_type=RecordType.ADR,
                module_name="auth",
                title="Test ADR",
                content="Content.",
            )
        ]
        await manager.record(
            agent_id, AgentRole.BUILDER, module_records=records
        )
        mock_module_store.insert_batch.assert_called_once()


class TestMemoryManagerLifecycle:
    """Tests for initialize/teardown."""

    @pytest.mark.asyncio
    async def test_initialize_creates_l1(
        self, manager, mock_working_store, agent_id
    ) -> None:
        """initialize() should create L1 state."""
        await manager.initialize(agent_id, AgentRole.BUILDER)
        mock_working_store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_teardown_deletes_l1(
        self, manager, mock_working_store, agent_id
    ) -> None:
        """teardown() should delete L1 state."""
        await manager.teardown(agent_id, AgentRole.BUILDER)
        mock_working_store.delete.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/memory/tests/integration/test_memory_manager.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `packages/memory/src/manager.py`:
```python
"""MemoryManager — Single entry point for the 3-layer memory system."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from packages.memory.src.compression.compressor import ContextCompressor
from packages.memory.src.compression.doc_sync import DocumentSyncer
from packages.memory.src.compression.promoter import MemoryPromoter
from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.semantic.models import MemoryContext, SearchResult
from packages.memory.src.working.models import WorkingState
from packages.shared.src.types.models import AgentRole, TournamentPhase

logger = logging.getLogger(__name__)


class MemoryManager:
    """One per team. Each agent gets its own L1, shares L2/L3 with teammates.

    Two main methods:
        recall() — before each LLM call, gather context from all 3 layers
        record() — after each LLM call, persist what happened
    """

    def __init__(
        self,
        team_id: UUID,
        tournament_id: UUID,
        working_store: object,
        module_store: object,
        semantic_store: object,
        compressor: ContextCompressor,
        promoter: MemoryPromoter,
        doc_syncer: DocumentSyncer,
    ) -> None:
        self._team_id = team_id
        self._tournament_id = tournament_id
        self._working = working_store
        self._module = module_store
        self._semantic = semantic_store
        self._compressor = compressor
        self._promoter = promoter
        self._doc_syncer = doc_syncer

    async def recall(
        self,
        agent_id: UUID,
        role: AgentRole,
        query: str,
        *,
        max_working_tokens: int = 2000,
        max_module_results: int = 5,
        max_semantic_results: int = 10,
    ) -> MemoryContext:
        """Retrieve context from all 3 layers before an LLM call."""
        # L1: Read working state
        working_state = await self._working.load(role)  # type: ignore[union-attr]
        if working_state is None:
            working_state = WorkingState(
                agent_id=agent_id,
                team_id=self._team_id,
                role=role,
                current_phase=TournamentPhase.BUILD,
            )

        # Check for overflow before returning context
        if await self._working.exceeds_threshold(role, threshold=max_working_tokens):  # type: ignore[union-attr]
            await self._handle_overflow(agent_id, role)
            working_state = await self._working.load(role)  # type: ignore[union-attr]
            if working_state is None:
                working_state = WorkingState(
                    agent_id=agent_id,
                    team_id=self._team_id,
                    role=role,
                    current_phase=TournamentPhase.BUILD,
                )

        # L2: Query module memory (hybrid SQL + full-text)
        module_results = await self._module.search_fulltext(  # type: ignore[union-attr]
            query, limit=max_module_results
        )

        # L3: Query semantic memory (Qdrant vector search)
        semantic_results = await self._semantic.search(  # type: ignore[union-attr]
            query, limit=max_semantic_results
        )

        # Estimate total tokens
        total_tokens = working_state.estimate_tokens()
        for r in module_results:
            total_tokens += len(r.content) // 4
        for s in semantic_results:
            total_tokens += len(s.snippet) // 4

        return MemoryContext(
            working_state=working_state,
            module_context=module_results,
            semantic_context=semantic_results,
            total_tokens_estimate=total_tokens,
        )

    async def record(
        self,
        agent_id: UUID,
        role: AgentRole,
        *,
        task: str | None = None,
        file_touched: str | None = None,
        decision: str | None = None,
        error: str | None = None,
        error_resolved: str | None = None,
        action_summary: str | None = None,
        module_records: list[ModuleRecord] | None = None,
    ) -> None:
        """Record what happened after an LLM call."""
        # Load current state (or create fresh)
        state = await self._working.load(role)  # type: ignore[union-attr]
        if state is None:
            state = WorkingState(
                agent_id=agent_id,
                team_id=self._team_id,
                role=role,
                current_phase=TournamentPhase.BUILD,
            )

        # Update L1 fields
        updates: dict = {"last_updated": datetime.now(timezone.utc)}
        if task is not None:
            updates["current_task"] = task
        if file_touched is not None:
            updates["current_file"] = file_touched
            files = list(state.recent_files_touched)
            files.append(file_touched)
            updates["recent_files_touched"] = files
        if decision is not None:
            decisions = list(state.recent_decisions)
            decisions.append(decision)
            updates["recent_decisions"] = decisions
        if error is not None:
            errors = list(state.active_errors)
            errors.append(error)
            updates["active_errors"] = errors
        if error_resolved is not None:
            errors = [e for e in state.active_errors if error_resolved not in e]
            updates["active_errors"] = errors

        updated_state = state.model_copy(update=updates)
        await self._working.save(updated_state)  # type: ignore[union-attr]

        # Persist module records to L2
        if module_records:
            await self._module.insert_batch(module_records)  # type: ignore[union-attr]

        # Log action to L2
        if action_summary:
            log_record = ModuleRecord(
                team_id=self._team_id,
                tournament_id=self._tournament_id,
                record_type=RecordType.ACTION_LOG,
                module_name="general",
                title=action_summary[:200],
                content=action_summary,
                agent_id=agent_id,
                agent_role=role,
            )
            await self._module.insert(log_record)  # type: ignore[union-attr]

    async def _handle_overflow(self, agent_id: UUID, role: AgentRole) -> None:
        """Compress + Promote + Doc Sync when L1 exceeds threshold."""
        state = await self._working.load(role)  # type: ignore[union-attr]
        if state is None:
            return

        # 1. Promote important items from L1 to L2
        promoted_records = self._promoter.promote(
            state, tournament_id=self._tournament_id
        )
        if promoted_records:
            await self._module.insert_batch(promoted_records)  # type: ignore[union-attr]

        # 2. Compress L1 via Haiku
        compressed = await self._compressor.compress(state)
        updated_state = self._compressor.apply(state, compressed)
        await self._working.save(updated_state)  # type: ignore[union-attr]

        # 3. Sync new records to .md files
        if promoted_records:
            synced_ids = self._doc_syncer.sync(promoted_records)
            if synced_ids:
                await self._module.mark_synced(synced_ids)  # type: ignore[union-attr]

        logger.info(
            "Overflow handled for %s: promoted=%d, dropped=%d",
            role.value,
            len(promoted_records),
            compressed.dropped_count,
        )

    async def initialize(self, agent_id: UUID, role: AgentRole) -> None:
        """Initialize L1 for a new agent. Called at spawn time."""
        state = WorkingState(
            agent_id=agent_id,
            team_id=self._team_id,
            role=role,
            current_phase=TournamentPhase.BUILD,
        )
        await self._working.save(state)  # type: ignore[union-attr]
        logger.info("Initialized memory for agent %s (%s)", agent_id, role.value)

    async def teardown(self, agent_id: UUID, role: AgentRole) -> None:
        """Clear L1 for a terminated agent. L2/L3 persist."""
        await self._working.delete(role)  # type: ignore[union-attr]
        logger.info("Torn down L1 memory for agent %s (%s)", agent_id, role.value)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/memory/tests/integration/test_memory_manager.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add packages/memory/src/manager.py packages/memory/tests/integration/test_memory_manager.py
git commit -m "feat(memory): implement MemoryManager facade with recall/record/overflow"
```

---

## Task 17: Wire Into Existing Code — AgentTeamManager + main.py

**Files:**
- Modify: `packages/agents/src/teams/manager.py:44-67` (AgentProcess.__init__ + _process_message)
- Modify: `packages/agents/src/teams/manager.py:188-240` (AgentTeamManager.spawn_team + teardown_team)
- Modify: `packages/api/src/main.py:68-107` (lifespan service init)

- [ ] **Step 1: Add MemoryManager to AgentProcess**

In `packages/agents/src/teams/manager.py`, modify `AgentProcess.__init__` to accept an optional `memory` parameter, and modify `_process_message` to call `recall()` before and `record()` after LLM calls.

Update the imports at the top of the file — add:
```python
from packages.memory.src.manager import MemoryManager
```

Update `AgentProcess.__init__` — add `memory` parameter:
```python
class AgentProcess:
    """Represents a running agent process with Redis-backed communication."""

    def __init__(
        self,
        agent: Agent,
        system_prompt: str,
        workspace_path: str,
        mailbox: RedisMailbox,
        llm_client: object | None = None,
        memory: MemoryManager | None = None,
    ) -> None:
        self.agent = agent
        self.system_prompt = system_prompt
        self.workspace_path = workspace_path
        self._mailbox = mailbox
        self._llm_client = llm_client
        self._memory = memory
        self._task: asyncio.Task | None = None
```

Update `_process_message` — add recall before and record after LLM:
```python
    async def _process_message(self, message: AgentMessage) -> None:
        """Process a single message from the inbox via LLM."""
        logger.info(
            "Agent %s processing %s from %s",
            self.agent.role.value,
            message.message_type.value,
            message.from_agent.value,
        )
        self.agent.actions_count += 1

        if self._llm_client is None:
            logger.warning("Agent %s has no LLM client — skipping LLM call", self.agent.role.value)
            return

        # Recall memory context before LLM call
        memory_context_text = ""
        if self._memory is not None:
            try:
                query = json.dumps(message.payload)[:500]
                ctx = await self._memory.recall(self.agent.id, self.agent.role, query)
                memory_context_text = ctx.format_for_prompt()
            except Exception:
                logger.warning("Memory recall failed for %s", self.agent.role.value, exc_info=True)

        # Build conversation for LLM
        messages = [
            {"role": "system", "content": self.system_prompt},
        ]
        if memory_context_text:
            messages.append({"role": "system", "content": memory_context_text})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"[{message.message_type.value}] from {message.from_agent.value}:\n"
                    f"{json.dumps(message.payload)}"
                ),
            },
        )

        try:
            response = await self._llm_client.completion(
                messages=messages,
                model=self.agent.model,
                trace_name=f"agent.{self.agent.role.value}.{message.message_type.value}",
                trace_metadata={
                    "agent_id": str(self.agent.id),
                    "team_id": str(self.agent.team_id),
                    "message_type": message.message_type.value,
                },
            )

            # Track token usage
            self.agent.total_tokens_used += response.usage.total_tokens
            self.agent.total_cost_usd += response.usage.cost_usd

            # Record to memory after LLM call
            if self._memory is not None:
                try:
                    await self._memory.record(
                        self.agent.id,
                        self.agent.role,
                        action_summary=f"Processed {message.message_type.value} from {message.from_agent.value}",
                    )
                except Exception:
                    logger.warning("Memory record failed for %s", self.agent.role.value, exc_info=True)

            logger.debug(
                "Agent %s LLM response: %d tokens, $%.4f",
                self.agent.role.value,
                response.usage.total_tokens,
                response.usage.cost_usd,
            )

        except Exception:
            self.agent.errors_count += 1
            logger.exception("Agent %s LLM call failed", self.agent.role.value)
```

- [ ] **Step 2: Add MemoryManager creation to AgentTeamManager.spawn_team**

Update `AgentTeamManager.__init__` to accept `memory_factory` and update `spawn_team` to create and pass `MemoryManager`:

```python
class AgentTeamManager:
    """Manages all agent teams across tournaments."""

    def __init__(
        self,
        event_bus: EventBus,
        redis: aioredis.Redis | None = None,
        llm_client: object | None = None,
        memory_factory: object | None = None,
    ) -> None:
        self._events = event_bus
        self._redis = redis
        self._llm_client = llm_client
        self._memory_factory = memory_factory
        self._teams: dict[UUID, list[AgentProcess]] = {}
        self._mailboxes: dict[UUID, RedisMailbox] = {}
        self._memory_managers: dict[UUID, MemoryManager] = {}
        self._watchers: dict[UUID, object] = {}
```

In `spawn_team`, after creating the mailbox and before the agent loop, add:
```python
        # Create shared MemoryManager for this team
        memory_mgr: MemoryManager | None = None
        if self._memory_factory is not None:
            try:
                memory_mgr = await self._memory_factory.create_for_team(
                    team_id=team_id,
                    tournament_id=tournament_id,
                    workspace_path=workspace_path,
                )
                self._memory_managers[team_id] = memory_mgr
                logger.info("Memory system initialized for team %s", team_id)
            except Exception:
                logger.warning("Memory system init failed for team %s", team_id, exc_info=True)
```

Then pass `memory=memory_mgr` to each `AgentProcess`:
```python
            process = AgentProcess(
                agent=agent,
                system_prompt=system_prompt,
                workspace_path=workspace_path,
                mailbox=mailbox,
                llm_client=self._llm_client,
                memory=memory_mgr,
            )
```

And add initialization for each agent:
```python
            if memory_mgr is not None:
                await memory_mgr.initialize(agent.id, agent_config.role)
```

In `teardown_team`, add memory cleanup before clearing mailboxes:
```python
        # Teardown memory (L1 only — L2/L3 persist)
        memory_mgr = self._memory_managers.get(team_id)
        if memory_mgr is not None:
            for ap in agents:
                await memory_mgr.teardown(ap.agent.id, ap.agent.role)
            del self._memory_managers[team_id]

        # Stop codebase watcher
        watcher = self._watchers.get(team_id)
        if watcher is not None:
            await watcher.stop()
            del self._watchers[team_id]
```

- [ ] **Step 3: Update main.py to initialize memory factory**

In `packages/api/src/main.py`, add after the Agent Team Manager initialization block (~line 87):

```python
    # Memory System Factory
    from packages.memory.src.manager import MemoryManager
    # Memory factory is injected into agent_manager (lazy init per team)
    # The memory stores are created per-team at spawn time using existing
    # Redis + DB connections from app.state
    app.state.agent_manager._memory_factory = None  # TODO: wire MemoryFactory in Task 18
    logger.info("Memory system available (lazy init per team)")
```

- [ ] **Step 4: Run existing tests to verify no regressions**

Run: `pytest packages/agents/tests/ -v`
Expected: All existing tests PASS (AgentProcess tests use `memory=None` default)

- [ ] **Step 5: Commit**

```bash
git add packages/agents/src/teams/manager.py packages/api/src/main.py
git commit -m "feat(memory): wire MemoryManager into AgentProcess and AgentTeamManager"
```

---

## Task 18: Full Test Suite Run + Lint

**Files:**
- All files in `packages/memory/`

- [ ] **Step 1: Run full memory package tests**

Run: `pytest packages/memory/ -v --cov=packages/memory --cov-report=term-missing`
Expected: All tests PASS, coverage >= 85%

- [ ] **Step 2: Run linter**

Run: `ruff check packages/memory/ --fix && ruff format packages/memory/`
Expected: No errors after auto-fix

- [ ] **Step 3: Run type checker**

Run: `mypy packages/memory/src/ --ignore-missing-imports`
Expected: No critical errors (some `type: ignore` for mock objects acceptable)

- [ ] **Step 4: Run existing project tests for regressions**

Run: `pytest packages/agents/tests/ packages/shared/tests/ packages/api/tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "test(memory): full test suite pass + lint + typecheck"
```

---

## Summary

| Task | Component | Tests | Key Files |
|------|-----------|-------|-----------|
| 1 | Dependencies | - | `pyproject.toml` |
| 2 | Package scaffold | - | `packages/memory/` structure + `CLAUDE.md` |
| 3 | WorkingState model | 7 | `working/models.py` |
| 4 | RecordType + ModuleRecord | 5 | `module/models.py` |
| 5 | CodeChunk + MemoryContext | 6 | `semantic/models.py` |
| 6 | L1 Redis store | 7 | `working/store.py` |
| 7 | L2 PostgreSQL store | 5 | `module/store.py`, `module/queries.py` |
| 8 | L3 Qdrant store | 6 | `semantic/store.py` |
| 9 | Hybrid embedder | 4 | `semantic/embedder.py` |
| 10 | Grammar loader | 6 | `indexer/grammars.py` |
| 11 | Code parser | 7 | `indexer/parser.py` |
| 12 | Memory promoter | 7 | `compression/promoter.py` |
| 13 | Context compressor | 5 | `compression/compressor.py` |
| 14 | Document syncer | 7 | `compression/doc_sync.py` |
| 15 | Indexing pipeline + watcher | 4 | `indexer/pipeline.py`, `indexer/watcher.py` |
| 16 | MemoryManager facade | 8 | `manager.py` |
| 17 | Integration wiring | existing | `manager.py`, `main.py` |
| 18 | Full test suite + lint | all | - |

**Total: 18 tasks, ~89 tests, 25 new files, 2 modified files.**
