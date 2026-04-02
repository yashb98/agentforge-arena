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
