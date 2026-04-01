# Plans 5-10: Lightweight Outlines

> Brief outlines for future features. Will be expanded into full specs when we reach them.

---

## Plan 5: Research Engine

**Goal:** Implement GitHub, arXiv, and web search for the research phase.

**Key files:**
- `packages/research/src/aggregator/sweep.py` — data structures exist, no search implementations
- New: `packages/research/src/github/searcher.py` — GitHub API search via httpx
- New: `packages/research/src/arxiv/searcher.py` — arXiv API search
- New: `packages/research/src/web/scraper.py` — Web scraping with httpx + BeautifulSoup

**Scope:**
- GitHub repo search by topic/language/stars
- arXiv paper search by keyword
- Web scraping for documentation/blog posts
- Aggregate results into `ResearchReport` (already defined)
- Rate limiting and caching (Redis)
- Integrate with agent research phase — agents call research tools

**Depends on:** Plan 2 (LLM for summarization), Plan 4 (Redis for caching)

---

## Plan 6: Sandbox Security

**Goal:** Implement AgentShield pre-execution scanning and network policies.

**Key files:**
- `packages/sandbox/src/docker/manager.py` — framework exists
- New: `packages/sandbox/src/security/agentshield.py` — pre-execution scanner
- New: `packages/sandbox/src/security/network_policy.py` — allowlist enforcement
- New: `packages/sandbox/src/security/resource_monitor.py` — CPU/RAM/disk tracking

**Scope:**
- 14-pattern secret scanner (AWS keys, API tokens, SSH keys, etc.)
- Privilege escalation detection (sudo, chmod 777, nsenter)
- Container escape detection (docker run, mount /proc)
- Data exfiltration detection (curl to non-whitelisted domains)
- Network allowlist enforcement per Rule 02-security
- Resource limit enforcement (4GB RAM, 2 vCPU, 10GB disk)
- Integration as PreToolUse hook

**Depends on:** Plan 1 (sandbox manager initialized)

---

## Plan 7: LLM Judge Evaluators

**Goal:** Make LLM judges actually read code and produce meaningful scores.

**Key files:**
- `packages/judge/src/scoring/service.py` — LLMJudge stubs
- New: `packages/judge/src/llm/ux_reviewer.py` — Screenshot + code review
- New: `packages/judge/src/llm/architecture_reviewer.py` — ARCHITECTURE.md review
- New: `packages/judge/src/llm/innovation_scorer.py` — Novel approach detection

**Scope:**
- Read actual source files from workspace (not just path references)
- UX: read frontend code + take screenshots via Playwright headless browser
- Architecture: parse ARCHITECTURE.md + analyze code structure
- Innovation: compare against common patterns, identify novel approaches
- Use tool_use for structured output (forced JSON schema)
- Temperature=0 for reproducibility
- Cross-review integration: weight peer review scores

**Depends on:** Plan 2 (LLMClient), Plan 3 (challenge scoring configs)

---

## Plan 8: Next.js Frontend

**Goal:** Build the spectator dashboard and tournament management UI.

**Key files:**
- `packages/web/` — currently empty (only CLAUDE.md)

**Scope:**
- Next.js 15 App Router with React 19
- Pages: dashboard, tournament list, tournament detail, spectator view, leaderboard
- Real-time: Socket.IO client for WebSocket spectator
- Components: terminal viewer (xterm.js), code viewer (Monaco), agent activity cards
- Charts: ELO history, score breakdowns (Recharts or D3)
- Styling: Tailwind CSS + shadcn/ui
- Dark mode default (arena/gaming aesthetic)

**Depends on:** Plan 1 (API endpoints working), Plan 6 (spectator WebSocket)

---

## Plan 9: Replay System

**Goal:** Export tournament event streams as replayable timelines.

**Key files:**
- `packages/replay/` — currently empty (only CLAUDE.md)
- `packages/shared/src/events/bus.py` — `replay()` method already exists

**Scope:**
- Export events from Redis Streams for a completed tournament
- Build timeline data structure with phases, agent actions, scores
- Langfuse trace integration — link LLM calls to timeline events
- Playback API: serve events at adjustable speed
- Frontend component: timeline slider with event markers

**Depends on:** Plan 1 (events flowing), Plan 8 (frontend to display)

---

## Plan 10: E2E Tournament Test

**Goal:** Run a complete 2-team duel end-to-end through all 8 phases.

**Key files:**
- New: `tests/e2e/test_tournament_duel.py`
- `Makefile` — `tournament-duel` target

**Scope:**
- Spin up all services (DB, Redis, LiteLLM) via docker-compose
- Create tournament via API
- Start tournament, verify phase transitions
- Mock agent LLM responses (recorded fixtures for determinism)
- Verify judging produces scores
- Verify ELO updates
- Verify event stream contains all expected events
- Verify cleanup (sandboxes destroyed, mailboxes cleared)
- Target: <5 minutes for full duel

**Depends on:** Plans 1-4 (all core wiring), Plan 3 (at least 1 challenge)

---

## Dependency Graph

```
Plan 1 (API wiring) ─────────────────┐
    │                                  │
Plan 2 (LLM) ──── depends on 1 ──────┤
    │                                  │
Plan 3 (Challenges) ── independent ───┤
    │                                  │
Plan 4 (Redis mailbox) ─ depends 1 ──┤
    │                                  │
Plan 5 (Research) ── depends 2, 4 ────┤
Plan 6 (Sandbox security) ─ dep 1 ───┤
Plan 7 (LLM judges) ── dep 2, 3 ─────┤
Plan 8 (Frontend) ── depends 1 ───────┤
Plan 9 (Replay) ── depends 1, 8 ──────┤
Plan 10 (E2E) ── depends 1-4 ─────────┘
```

**Recommended execution order:** 1 → 3 (parallel with 1) → 2 → 4 → 5 & 6 (parallel) → 7 → 8 → 9 → 10
