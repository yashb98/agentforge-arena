# Agent Memory System — Design Spec

> **P0 infrastructure** for enabling multi-day (48-72h), 50-100k LOC tournament builds.
> Without persistent memory, agents can't survive past ~2 hours of continuous work.

**Date:** 2026-04-02
**Status:** Approved
**Package:** `packages/memory/`

---

## 1. Problem Statement

Current agents (`AgentProcess` in `packages/agents/src/teams/manager.py`) are stateless between LLM calls. They process a message, call the LLM, and forget everything. After ~50 calls the context window fills and agents lose track of what they built hours ago.

For 50-100k LOC multi-day tournaments, agents need:
- **Working memory** that persists across LLM calls within a sprint
- **Structured memory** that survives context rotations and agent crashes
- **Semantic search** over the codebase so agents can navigate 100k LOC without reading every file
- **Self-healing documentation** so every `.md` file in the project stays current

---

## 2. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Embedding model | **Hybrid** — FastEmbed (local ONNX) for bulk indexing, LiteLLM for query-time | Indexing 50-100k LOC via API costs $5-20 per reindex. Local is free. Queries benefit from higher quality. |
| Language support | **Dynamic grammar loading** — lazy-load tree-sitter grammars per file extension | Different challenges use different stacks. Only pay for what's used. |
| Context overflow | **Compress + Promote** — Haiku summary + promote important items to L2/L3 | Summaries keep agents coherent. Promotion means nothing is truly lost. |
| Re-indexing strategy | **Debounced file-watch** — batch re-index every 60 seconds | Always fresh (max 60s stale), avoids thrashing on rapid edits. |
| Architecture | **Embedded library** — new `packages/memory/` package | Follows monorepo pattern. Testable in isolation. No new infrastructure services. |
| Doc sync scope | **All project .md files** — rules, gotchas, agents, hooks, architecture, status | Project accumulates intelligence continuously. Agent crashes cause zero knowledge loss. |

---

## 3. Three-Layer Memory Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent LLM Call                            │
│  recall() → [L1 + L2 + L3 context] → prompt → response → record()  │
└──────┬──────────────┬──────────────┬────────────────────────────┘
       │              │              │
       ▼              ▼              ▼
┌─────────────┐ ┌──────────────┐ ┌──────────────────────────┐
│ L1: Working │ │ L2: Module   │ │ L3: Semantic             │
│ Memory      │ │ Memory       │ │ Memory                   │
│             │ │              │ │                          │
│ Redis Hash  │ │ PostgreSQL   │ │ Qdrant                   │
│ + JSON      │ │ + pgvector   │ │ + FastEmbed/LiteLLM      │
│             │ │ + full-text  │ │ + tree-sitter            │
│ Per-agent   │ │ Per-team     │ │ Per-team                 │
│ TTL: sprint │ │ TTL: tourney │ │ TTL: tourney             │
└─────────────┘ └──────────────┘ └──────────────────────────┘
       │              ▲              ▲
       │    promote    │    index     │
       └──────────────►│◄────────────┘
                       │
                  ┌────▼────┐
                  │ DocSync │ → .md files
                  └─────────┘
```

### L1: Working Memory (Redis)

**Scope:** Per-agent. Hot state refreshed every LLM call.
**Storage:** Redis Hash for flat fields + Redis JSON for nested data.
**TTL:** Expires at sprint boundary or agent termination.

```
Redis key: working:{team_id}:{agent_role}

Fields (Hash):
  current_task         "TASK-003: Implement auth endpoints"
  current_file         "src/api/auth.py"
  current_phase        "build"
  token_budget_used    "4523"
  last_updated         "2026-04-02T14:30:00Z"

Redis key: working:{team_id}:{agent_role}:json

Fields (JSON):
  recent_decisions[]     Last 10 decisions (capped, FIFO)
  recent_files_touched[] Last 20 files (capped, FIFO)
  active_errors[]        Unresolved errors (uncapped)
  context_summary        Compressed summary from overflow handler
```

### L2: Module Memory (PostgreSQL + pgvector)

**Scope:** Per-team. Structured records that survive agent crashes.
**Storage:** Single `module_memory` table with `record_type` discriminator, JSONB metadata, vector column.
**Indexes:** HNSW on embedding column, GIN on `ts_vector` full-text column, B-tree on `record_type`, `module_name`, `team_id`.

```sql
CREATE TABLE module_memory (
    id              UUID PRIMARY KEY,
    team_id         UUID NOT NULL,
    tournament_id   UUID NOT NULL,
    record_type     VARCHAR(30) NOT NULL,   -- 'adr', 'gotcha', 'coding_pattern', etc.
    module_name     VARCHAR(100) NOT NULL,
    file_path       VARCHAR(500),
    title           VARCHAR(500) NOT NULL,
    content         TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}',
    agent_id        UUID,
    agent_role      VARCHAR(30),
    ts_vector       TSVECTOR,               -- Full-text search
    embedding       VECTOR(384),            -- Semantic search via pgvector
    synced_to_docs  BOOLEAN DEFAULT FALSE,  -- Track if doc_sync has processed this
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_module_memory_team ON module_memory(team_id, record_type);
CREATE INDEX ix_module_memory_module ON module_memory(module_name);
CREATE INDEX ix_module_memory_embedding ON module_memory
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX ix_module_memory_fts ON module_memory USING gin(ts_vector);
```

### L3: Semantic Memory (Qdrant + FastEmbed + tree-sitter)

**Scope:** Per-team. Vector search over the codebase.
**Storage:** Qdrant collection per team with named vectors + sparse vectors.
**Embedding:** FastEmbed (`BAAI/bge-small-en-v1.5`, 384-dim) for indexing. LiteLLM for queries.

```python
# Qdrant collection config
collection_name = f"code_search_{team_id}"

vectors_config = {
    "code": VectorParams(size=384, distance=Distance.COSINE),
    "docstring": VectorParams(size=384, distance=Distance.COSINE),
}
sparse_vectors_config = {
    "keywords": SparseVectorParams(modifier=Modifier.IDF),
}
quantization_config = ScalarQuantization(
    scalar=ScalarQuantizationConfig(type=ScalarType.INT8, quantile=0.99, always_ram=True)
)

# Payload schema per point
payload = {
    "file_path": "src/api/auth.py",
    "module_name": "auth",
    "language": "python",
    "symbol_name": "AuthService.login",
    "symbol_type": "method",         # function, class, method, module
    "line_start": 42,
    "line_end": 78,
    "dependencies": ["src/models/user.py", "src/services/jwt.py"],
}
```

---

## 4. Record Types

```python
class RecordType(str, Enum):
    FILE_META       = "file_meta"        # What a file does, its interfaces
    ADR             = "adr"              # Architecture decision
    TECH_DEBT       = "tech_debt"        # Known bugs, workarounds, shortcuts
    SIGNATURE       = "signature"        # Function/class signature
    ACTION_LOG      = "action_log"       # What agent did and when
    DEPENDENCY      = "dependency"       # Module dependency relationship
    GOTCHA          = "gotcha"           # Runtime pitfalls, footguns
    CODING_PATTERN  = "coding_pattern"   # Discovered coding rules
    AGENT_LEARNING  = "agent_learning"   # Role-specific knowledge
    HOOK_DISCOVERY  = "hook_discovery"   # Validated hook/formatter commands
```

---

## 5. Data Models

### L1: Working State

```python
class WorkingState(BaseModel):
    agent_id: UUID
    team_id: UUID
    role: AgentRole
    current_phase: TournamentPhase
    current_task: str | None = None
    current_file: str | None = None
    recent_decisions: list[str] = []         # Capped at 10
    recent_files_touched: list[str] = []     # Capped at 20
    active_errors: list[str] = []            # Uncapped
    context_summary: str = ""                # Compressed summary
    token_budget_used: int = 0
    last_updated: datetime
```

### L2: Module Record

```python
class ModuleRecord(BaseModel):
    id: UUID
    team_id: UUID
    tournament_id: UUID
    record_type: RecordType
    module_name: str
    file_path: str | None = None
    title: str
    content: str
    metadata: dict[str, Any] = {}
    agent_id: UUID | None = None
    agent_role: AgentRole | None = None
    synced_to_docs: bool = False
    created_at: datetime
    updated_at: datetime
```

### L3: Code Chunk

```python
class CodeChunk(BaseModel):
    chunk_id: str                     # "{file_path}::{symbol_name}"
    file_path: str
    language: str
    module_name: str
    symbol_name: str | None = None
    symbol_type: str | None = None    # function, class, method, module
    content: str
    docstring: str | None = None
    line_start: int
    line_end: int
    dependencies: list[str] = []
```

### Search Result

```python
class SearchResult(BaseModel):
    source: str                       # "module" or "semantic"
    score: float
    chunk: CodeChunk | None = None
    record: ModuleRecord | None = None
    snippet: str                      # Formatted for prompt injection
```

### Memory Context (returned by recall)

```python
class MemoryContext(BaseModel):
    working_state: WorkingState
    module_context: list[ModuleRecord]
    semantic_context: list[SearchResult]
    total_tokens_estimate: int

    def format_for_prompt(self) -> str:
        """Format all 3 layers into structured text for LLM prompt."""
```

---

## 6. MemoryManager Facade (Public API)

The single entry point. Two main methods: `recall()` before LLM calls, `record()` after.

```python
class MemoryManager:
    """One per team. Each agent gets its own L1, shares L2/L3 with teammates."""

    def __init__(
        self,
        team_id: UUID,
        tournament_id: UUID,
        working_store: WorkingMemoryStore,
        module_store: ModuleMemoryStore,
        semantic_store: SemanticStore,
        compressor: ContextCompressor,
        promoter: MemoryPromoter,
        doc_syncer: DocumentSyncer,
    ) -> None: ...

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
        """Retrieve context from all 3 layers before an LLM call.

        Flow:
          1. Read L1 working state
          2. Query L2 (hybrid SQL + vector) for matching module records
          3. Query L3 (Qdrant hybrid search) for relevant code chunks
          4. If L1 exceeds max_working_tokens → trigger overflow handler
          5. Merge and return MemoryContext
        """

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
        """Record what happened after an LLM call.

        Flow:
          1. Update L1 working state
          2. Persist module_records to L2 if provided
          3. Log action_summary to L2 as ACTION_LOG
        """

    async def _handle_overflow(self, agent_id: UUID, role: AgentRole) -> None:
        """Compress + Promote + Doc Sync when L1 exceeds threshold.

        Flow:
          1. Promoter scans L1 → creates L2 records (ADR, GOTCHA, PATTERN, etc.)
          2. Compressor calls Haiku → compresses L1 into summary
          3. DocSyncer routes new L2 records to appropriate .md files
          4. L1 state updated: summary replaces verbose items
        """

    async def initialize(self, agent_id: UUID, role: AgentRole) -> None:
        """Initialize L1 for a new agent. Called at spawn time."""

    async def teardown(self, agent_id: UUID) -> None:
        """Clear L1 for a terminated agent. L2/L3 persist."""

    async def checkpoint(self) -> str:
        """Snapshot all memory layers to MinIO. Returns snapshot ID."""

    async def restore(self, snapshot_id: str) -> None:
        """Restore memory from a MinIO snapshot."""
```

---

## 7. Code Indexer (tree-sitter + Embeddings Pipeline)

Background process that keeps L3 fresh as agents write code.

### Watcher

```python
class CodebaseWatcher:
    """Debounced file-watch loop. Runs as asyncio.Task per team.

    Every 60 seconds:
      1. Scan workspace for changed files (mtime-based)
      2. Batch changed files into the indexing pipeline
      3. Track last-indexed mtime per file to avoid re-processing
    """
    DEBOUNCE_SECONDS = 60
    SUPPORTED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".md"}
```

### Parser

```python
class CodeParser:
    """Tree-sitter AST parser. Extracts semantic chunks from source files.

    Chunking strategy per language:
      Python:     function_definition, class_definition
      TS/JS:      function_declaration, class_declaration, arrow_function, export
      Go:         function_declaration, method_declaration, type_spec (struct)
      Rust:       function_item, impl_item, struct_item, enum_item
      Markdown:   ATX headings (## sections)

    Files < 50 lines:   single chunk (whole file)
    Files > 500 lines with no parseable symbols: 100-line sliding windows
    """
```

### Grammar Loader

```python
class GrammarLoader:
    """Lazy-loads tree-sitter grammars. Cached after first use per language.

    Extension → Language mapping:
      .py         → python
      .ts, .tsx   → typescript
      .js, .jsx   → javascript
      .go         → go
      .rs         → rust
    """
```

### Hybrid Embedder

```python
class HybridEmbedder:
    """FastEmbed for bulk indexing (free, local). LiteLLM for queries (higher quality).

    Indexing: BAAI/bge-small-en-v1.5 via FastEmbed (384-dim, ONNX, CPU)
    Queries:  LiteLLM proxy embedding call (384-dim compatible model)
    Fallback: If LiteLLM unavailable, queries also use FastEmbed
    """
```

### Indexing Pipeline

```python
class IndexingPipeline:
    """Parse → chunk → embed → upsert.

    Flow for a batch of changed files:
      1. Parse each file via tree-sitter → list[CodeChunk]
      2. Embed code content via FastEmbed (batch, local)
      3. Embed docstrings via FastEmbed (batch, local)
      4. Upsert to Qdrant: named vectors (code, docstring) + sparse (keywords) + payload
      5. Upsert file metadata to L2 as FILE_META records
      6. Delete Qdrant points for removed files
    """
```

---

## 8. Compression & Overflow Handling

### Context Compressor

```python
class ContextCompressor:
    """Haiku 4.5 summarization when L1 exceeds token threshold.

    Trigger: L1 working state > 2000 tokens (estimated)
    Model:   claude-haiku-4-5 (fastest, cheapest)
    Cost:    ~$0.001 per compression
    Latency: ~500ms

    Prompt strategy:
      "Summarize this agent's working state into a dense paragraph.
       Preserve: current task, key decisions, unresolved errors, files modified.
       Drop: routine actions, redundant info, resolved issues."

    Output:
      CompressedContext:
        summary: str              (~500 tokens)
        preserved_decisions: list  (top 3 kept verbatim)
        dropped_count: int
    """
```

### Memory Promoter

```python
class MemoryPromoter:
    """Promotes important L1 items to L2 before compression. Deterministic rules, no LLM.

    Promotion rules (keyword matching + frequency):
      "chose/decided/architecture/design"                → RecordType.ADR
      "bug/fix/workaround/hack"                          → RecordType.TECH_DEBT
      "gotcha/careful/don't/never/always/footgun/breaks" → RecordType.GOTCHA
      "pattern/convention/must use/should use/prefer"    → RecordType.CODING_PATTERN
      "learned/discovered/realized/turns out"            → RecordType.AGENT_LEARNING
      "formatter/linter/hook/auto-format/pre-commit"     → RecordType.HOOK_DISCOVERY
      Resolved errors                                    → RecordType.ACTION_LOG
      Files touched > 3 times                            → RecordType.FILE_META
      Cross-module mentions                              → RecordType.DEPENDENCY
    """
```

---

## 9. Document Sync (Self-Healing .md Files)

Every `.md` file in the project is kept in sync with accumulated memory. The project gets smarter over time.

### Routing Table

```
RecordType          → Target Files
────────────────────────────────────────────────────────────────────
ADR                 → DECISIONS.md, .claude/memory/decisions-log.md
TECH_DEBT           → TECH_DEBT.md, .claude/rules/gotchas.md, .claude/memory/gotchas.md
GOTCHA              → .claude/rules/gotchas.md, .claude/memory/gotchas.md
CODING_PATTERN      → .claude/rules/project-rules.md, .claude/rules/stack-rules.md
AGENT_LEARNING      → .claude/agents/{role}-notes.md
HOOK_DISCOVERY      → .claude/hooks/{hook}.sh
DEPENDENCY          → ARCHITECTURE.md (Haiku, only if graph changed)
ACTION_LOG          → STATUS.md (Haiku regen)
FILE_META           → CLAUDE.md (Haiku, only if significant new modules)
```

### Sync Strategies

| Target | Strategy | LLM? | Trigger |
|--------|----------|------|---------|
| DECISIONS.md | Append new ADRs in numbered format | No | Each compression cycle |
| TECH_DEBT.md | Append new items | No | Each compression cycle |
| .claude/rules/gotchas.md | Append `G-{n}: title` format with symptom/cause/fix | No | Each compression cycle |
| .claude/rules/project-rules.md | Append, deduplicate against existing | No | Each compression cycle |
| .claude/rules/stack-rules.md | Append stack-specific patterns | No | Each compression cycle |
| .claude/agents/{role}-notes.md | Append role-specific learnings | No | Each compression cycle |
| .claude/memory/decisions-log.md | Append chronological log | No | Each compression cycle |
| .claude/memory/gotchas.md | Append gotchas | No | Each compression cycle |
| .claude/hooks/*.sh | Create/update hook scripts | No | On HOOK_DISCOVERY |
| STATUS.md | Regenerate from L2 action logs | Yes (Haiku) | Each compression + sprint boundary |
| ARCHITECTURE.md | Update component diagram | Yes (Haiku) | Only when DEPENDENCY records change |
| CLAUDE.md | Update key files, commands, context | Yes (Haiku) | Only when significant new modules added |
| RESEARCH.md | Append new findings | No | When researcher agent produces findings |

### Gotcha Format

```markdown
## G-001: Redis needs retry wrapper on all connections
**Discovered:** 2026-04-02 14:30 | **Agent:** Builder
**Symptom:** Random ConnectionError after 5+ minutes idle
**Cause:** Redis drops idle connections; our pool doesn't reconnect
**Fix:** Wrap all Redis calls with `tenacity.retry(stop=stop_after_attempt(3))`
**Files affected:** src/services/cache.py, src/api/middleware.py
```

### ADR Format

```markdown
## ADR-003: Chose bcrypt over argon2 for password hashing
**Date:** 2026-04-02 16:15 | **Agent:** Builder
**Context:** Need password hashing for auth endpoints
**Decision:** bcrypt — simpler API, well-supported, good enough security
**Consequences:** Slightly slower than argon2 at high parallelism, acceptable for our scale
```

---

## 10. Integration Points (Existing Code Changes)

Only 2 files need modification in existing code:

### `packages/agents/src/teams/manager.py`

```python
# In AgentTeamManager.spawn_team():
#   1. Create shared memory stores (L2, L3) for the team
#   2. Create per-agent L1 store
#   3. Create MemoryManager
#   4. Start CodebaseWatcher as background task
#   5. Pass MemoryManager to each AgentProcess

# In AgentProcess._process_message():
#   1. Before LLM call: context = await self._memory.recall(...)
#   2. Inject context.format_for_prompt() into messages
#   3. After LLM call: await self._memory.record(...)

# In AgentTeamManager.teardown_team():
#   1. Stop CodebaseWatcher
#   2. Teardown per-agent L1
#   3. L2/L3 persist for post-tournament analysis
```

### `packages/shared/src/types/models.py`

```python
# Add RecordType enum (or import from memory package)
# No changes to existing models
```

---

## 11. Package Structure

```
packages/memory/
├── __init__.py
├── CLAUDE.md
├── src/
│   ├── __init__.py
│   ├── manager.py                  ← MemoryManager facade
│   ├── working/
│   │   ├── __init__.py
│   │   ├── store.py                ← WorkingMemoryStore (Redis)
│   │   └── models.py              ← WorkingState, AgentContext
│   ├── module/
│   │   ├── __init__.py
│   │   ├── store.py                ← ModuleMemoryStore (PostgreSQL + pgvector)
│   │   ├── models.py              ← ModuleRecord, RecordType
│   │   └── queries.py             ← Hybrid SQL + vector query builders
│   ├── semantic/
│   │   ├── __init__.py
│   │   ├── store.py                ← SemanticStore (Qdrant)
│   │   ├── models.py              ← CodeChunk, SearchResult, MemoryContext
│   │   └── embedder.py            ← HybridEmbedder (FastEmbed + LiteLLM)
│   ├── indexer/
│   │   ├── __init__.py
│   │   ├── watcher.py             ← CodebaseWatcher (debounced 60s loop)
│   │   ├── parser.py              ← CodeParser (tree-sitter)
│   │   ├── grammars.py            ← GrammarLoader (lazy, per-language)
│   │   └── pipeline.py            ← IndexingPipeline (parse → embed → upsert)
│   └── compression/
│       ├── __init__.py
│       ├── compressor.py          ← ContextCompressor (Haiku summarization)
│       ├── promoter.py            ← MemoryPromoter (L1 → L2, deterministic)
│       └── doc_sync.py            ← DocumentSyncer (L2 → .md files)
├── tests/
│   ├── conftest.py                ← fakeredis, test DB, mock Qdrant, fixtures
│   ├── unit/
│   │   ├── test_working_store.py
│   │   ├── test_module_store.py
│   │   ├── test_semantic_store.py
│   │   ├── test_parser.py
│   │   ├── test_grammars.py
│   │   ├── test_embedder.py
│   │   ├── test_compressor.py
│   │   ├── test_promoter.py
│   │   └── test_doc_sync.py
│   └── integration/
│       ├── test_memory_manager.py
│       └── test_indexer_pipeline.py
```

---

## 12. New Dependencies

Add to `pyproject.toml`:

```toml
# Agent Memory System
"fastembed>=0.5.0",                # Local ONNX embeddings (no GPU needed)
"tree-sitter>=0.25.0",            # AST parsing
"tree-sitter-python>=0.25.0",     # Python grammar
"tree-sitter-javascript>=0.25.0", # JS grammar
"tree-sitter-typescript>=0.25.0", # TypeScript grammar
```

All other dependencies (redis, qdrant-client, pgvector, sqlalchemy, litellm, orjson, boto3, langfuse) are already in the project.

---

## 13. Infrastructure

No new services. Uses existing docker-compose stack:

| Service | Port | Used For |
|---------|------|----------|
| Redis 7 | 6379 | L1 working memory (Hash + JSON + TTL) |
| PostgreSQL 16 + pgvector | 5432 | L2 module memory (SQL + vector + full-text) |
| Qdrant | 6333 | L3 semantic memory (vector search + sparse) |
| MinIO | 9000 | Memory checkpoint snapshots |
| Langfuse | 3001 | Trace memory operations |

### Redis Configuration Note

Current Redis config (`docker-compose.yml:38`) sets `maxmemory 512mb` with `allkeys-lru`. Working memory for 25 agents across 8 teams ≈ 50MB — well within limits. No changes needed.

### PostgreSQL Migration

One new table: `module_memory` (see Section 3). Create via Alembic migration.

### Qdrant Collection

Created dynamically per team at tournament start. Destroyed at tournament end. Snapshot to MinIO at checkpoints.

---

## 14. Performance Estimates

| Operation | Latency | Cost |
|-----------|---------|------|
| L1 recall (Redis read) | <1ms | Free |
| L1 record (Redis write) | <1ms | Free |
| L2 recall (PostgreSQL hybrid query) | 5-20ms | Free |
| L2 record (PostgreSQL insert) | 2-5ms | Free |
| L3 recall (Qdrant search) | 10-30ms | Free |
| L3 index (FastEmbed + Qdrant upsert, per file) | 50-200ms | Free |
| Full codebase index (10k chunks) | 30-60s | Free |
| Context compression (Haiku call) | 500-1000ms | ~$0.001 |
| Doc sync (deterministic appends) | 5-20ms | Free |
| Doc sync (Haiku regen STATUS.md) | 500-1000ms | ~$0.001 |
| Total overhead per LLM call | 15-50ms | Free |

Memory overhead per team:
- L1 Redis: ~2MB (25 agents max)
- L2 PostgreSQL: ~200MB (100k records with vectors)
- L3 Qdrant: ~50-100MB (10k code chunks, INT8 quantized)

---

## 15. Overflow Flow (End-to-End)

```
Agent L1 working memory exceeds 2000 tokens (checked on every recall())
  │
  ├─ 1. Promoter scans L1 state (deterministic keyword matching)
  │     → Creates L2 records: ADR, GOTCHA, CODING_PATTERN, AGENT_LEARNING, etc.
  │
  ├─ 2. Compressor calls Haiku (~$0.001, ~500ms)
  │     → recent_decisions (15 items) → compressed summary (~500 tokens)
  │     → Preserves top 3 decisions verbatim
  │
  ├─ 3. L1 state updated:
  │     → context_summary = compressed summary
  │     → recent_decisions = only preserved decisions
  │     → recent_files_touched = trimmed to last 10
  │     → active_errors = unchanged (never compress errors)
  │
  ├─ 4. DocSyncer routes new L2 records to .md files:
  │     ├─ ADR → DECISIONS.md + .claude/memory/decisions-log.md
  │     ├─ GOTCHA → .claude/rules/gotchas.md + .claude/memory/gotchas.md
  │     ├─ CODING_PATTERN → .claude/rules/project-rules.md
  │     ├─ AGENT_LEARNING → .claude/agents/{role}-notes.md
  │     ├─ HOOK_DISCOVERY → .claude/hooks/{hook}.sh
  │     ├─ TECH_DEBT → TECH_DEBT.md
  │     ├─ ACTION_LOG → STATUS.md (Haiku regen)
  │     └─ DEPENDENCY → ARCHITECTURE.md (Haiku, only if changed)
  │
  └─ Result: Agent continues with lean L1 + rich L2/L3
             All .md files reflect accumulated knowledge
             Any replacement agent cold-boots with full context
```

---

## 16. Self-Healing Timeline Example

```
Hour  0: Architect bootstraps → generic CLAUDE.md, ARCHITECTURE.md, rules
Hour  6: Builder hits Redis bug → GOTCHA promoted → .claude/rules/gotchas.md updated
Hour 12: Tester finds async fixture issue → GOTCHA + PATTERN → rules updated
Hour 18: Compression triggered → STATUS.md regenerated, DECISIONS.md gets 5 ADRs
Hour 24: Builder crashes → replacement reads ALL updated .md files → zero knowledge loss
Hour 36: Compression triggered again → ARCHITECTURE.md updated (new modules in diagram)
Hour 48: Tournament ends → project has complete, accurate, self-generated documentation
```

---

## 17. Testing Strategy

| Layer | Test Type | What | Mock |
|-------|-----------|------|------|
| L1 WorkingMemoryStore | Unit | CRUD, TTL, overflow detection | fakeredis |
| L2 ModuleMemoryStore | Unit | CRUD, hybrid queries | Test PostgreSQL (pytest-postgresql) |
| L3 SemanticStore | Unit | Search, upsert, delete | Mock QdrantClient |
| CodeParser | Unit | Chunk extraction per language | Real tree-sitter (no mock needed) |
| GrammarLoader | Unit | Lazy loading, caching | Real tree-sitter |
| HybridEmbedder | Unit | Bulk + query paths | Mock FastEmbed + mock LiteLLM |
| ContextCompressor | Unit | Compression output format | Mock LLM client |
| MemoryPromoter | Unit | Keyword matching rules | None (pure logic) |
| DocumentSyncer | Unit | Routing, file formatting | Mock filesystem |
| MemoryManager | Integration | Full recall/record/overflow cycle | fakeredis + test DB + mock Qdrant |
| IndexingPipeline | Integration | Parse → embed → upsert end-to-end | Real tree-sitter + mock Qdrant |

Coverage target: **85%** (higher than default 80% — this is critical infrastructure).
