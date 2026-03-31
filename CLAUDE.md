# AgentForge Arena

> Competitive tournament platform — AI agent teams build production apps in hackathon-style challenges.
> v2.0.0 | Build Phase

## Core Loop

Challenge → Research → Architect → Build (sandboxed) → Cross-Review → Judge → Winner

## Tech Stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2
- **Frontend:** Next.js 15, React 19, TypeScript 5.5
- **DB:** PostgreSQL 16 + pgvector | **Cache/PubSub:** Redis 7 Streams
- **Sandbox:** Docker MicroVM per team | **Tracing:** Langfuse
- **LLM:** Each team gets its own Claude Code CLI instance (model-agnostic via LiteLLM proxy)
- **Search:** Qdrant | **Object Storage:** MinIO

## Critical Rules

1. **NEVER** run agent code outside a Docker Sandbox
2. **NEVER** expose API keys in sandboxes — LiteLLM proxy only
3. **ALWAYS** trace before execute (Langfuse trace ID required)
4. **ALWAYS** run security hooks before Bash/Write in sandboxes
5. Test coverage: 80% min (judge: 95%)
6. Type everything — Pydantic, TypeScript strict, no untyped `Any`
7. Events are immutable — corrections publish new events
8. Agents are stateless between phases

## Architecture

- **Event-driven + CQRS** — Redis Streams event bus
- **Package boundaries** — cross-package imports through `packages/shared/`
- **Agent isolation** — per-team MicroVM, role-based permissions, JSON mailbox comms
- **Claude Code as agent runtime** — each team runs its own Claude Code CLI, self-bootstrapping CLAUDE.md, rules, hooks, and skills for projects they build

## Packages

`core` (orchestration) | `sandbox` (Docker MicroVM) | `agents` (team lifecycle) | `judge` (scoring/ELO) | `spectator` (WebSocket streaming) | `api` (FastAPI gateway) | `web` (Next.js dashboard) | `replay` (Langfuse traces) | `research` (GitHub/arXiv) | `shared` (types, DB, Redis, Langfuse)

Each package has its own `CLAUDE.md` — read before working in it.

## Dev Commands

```bash
make setup && make dev        # Install + start services
make tournament-duel          # Local 2-team duel
pytest && ruff check . && mypy --strict  # Test + lint + typecheck
```

## References

- `.claude/rules/` — Global, quality, security, testing, architecture, agent boundaries
- `.claude/agents/` — Role definitions (architect, builder, critic, tester, researcher, etc.)
- `.claude/memory/decisions-log.md` — Architecture decisions
- `.claude/memory/gotchas.md` — Known pitfalls
