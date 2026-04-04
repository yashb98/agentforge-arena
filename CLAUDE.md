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
8. Agents are stateless between phases (orchestrator processes reset; deliverables persist on disk)

## Team project vs monorepo root

During a tournament, **all evolution happens inside each team’s sandbox project tree** — typically `{sandbox.workspace_base}/team-{uuid}/project/` (see `packages/sandbox`). Teams may add or change their own `CLAUDE.md`, `.claude/rules`, `.claude/hooks`, `.claude/skills`, `docs/decisions/`, `ARCHITECTURE.md`, specs, and application code **only under that project root**.

The **AgentForge Arena repository** (`packages/`, shared `challenges/library/`, and this repo’s `.claude/` used by human maintainers) is **not** the competition workspace. Tournament agents must not treat the monorepo root as their editable codebase unless you are explicitly doing platform development outside the sandbox rules above.

## Architecture

- **Event-driven + CQRS** — Redis Streams event bus
- **Package boundaries** — cross-package imports through `packages/shared/`
- **Agent isolation** — per-team MicroVM, role-based permissions, JSON mailbox comms
- **Claude Code as agent runtime** — each team runs its own Claude Code CLI, self-bootstrapping CLAUDE.md, rules, hooks, and skills for projects they build
- **Time pressure** — auto-timed phases publish periodic clock ticks and hard deadlines; teams are nudged to verify fresh research before substantive implementation
- **Sandbox autonomy** — each team project is seeded with permissive `.claude/settings.json` inside the MicroVM (trust boundary is the sandbox, not interactive approve-all in the host IDE)

## Packages

`core` (orchestration) | `sandbox` (Docker MicroVM) | `agents` (team lifecycle) | `judge` (scoring/ELO) | `spectator` (WebSocket streaming) | `api` (FastAPI gateway) | `web` (Next.js dashboard) | `replay` (Langfuse traces) | `research` (GitHub/arXiv) | `shared` (types, DB, Redis, Langfuse)

Each package has its own `CLAUDE.md` — read before working in it.

## Dev Commands

```bash
make setup && make dev        # Install + start services
make tournament-duel          # Local 2-team duel (headless CLI, same stack as API)
# or: python -m packages.core.src.tournament.cli start --format duel
#     arena-tournament start --format duel --agent-runtime arena_native
pytest && ruff check . && mypy --strict  # Test + lint + typecheck
```

## Code review graph ([code-review-graph](https://github.com/tirth8205/code-review-graph))

- **Monorepo (Cursor):** `.cursor/mcp.json` runs the MCP server via `uvx code-review-graph serve`. After `pip install -e ".[dev]"`, `code-review-graph` is on your PATH when the venv is active — hooks in `.claude/settings.json` call it for incremental updates.
- **First-time / refresh:** `code-review-graph build` from this repo root (graph lives in `.code-review-graph/`, gitignored). Tune skips in `.code-review-graphignore`.
- **Team sandboxes:** New `project/` trees get `.mcp.json`, `.code-review-graphignore`, and bundled skills (`build-graph`, `review-delta`, `review-pr`) under `.claude/skills/`. Inside a locked-down MicroVM, `uvx` may need PyPI access; otherwise install `code-review-graph` into the team venv and edit `.mcp.json` `command` to that binary.

Restart Cursor (or Claude Code) after MCP changes.

## Evaluation pipeline

- **Challenge contracts:** `make challenge-validate` (or `scripts/eval/validate_challenge_library.py`).
- **Golden + hidden tests:** `make golden-hidden-url-shortener` — reference app under `challenges/fixtures/url-shortener-saas/golden/`.
- **CI:** `.github/workflows/evaluation.yml` runs validation, golden hidden tests, and `pytest packages/`.

## References

- `.claude/rules/` — Global, quality, security, testing, architecture, agent boundaries
- `.claude/agents/` — Role definitions (architect, builder, critic, tester, researcher, etc.)
- `.claude/memory/decisions-log.md` — Architecture decisions
- `.claude/memory/gotchas.md` — Known pitfalls
