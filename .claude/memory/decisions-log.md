# Architecture Decision Records (ADR)

## ADR-001: Docker Sandbox MicroVM over Plain Docker
**Date**: 2026-03-31
**Status**: Accepted
**Context**: Need hardware-level isolation between competing teams. Plain Docker
shares the kernel — a container escape could access another team's code.
**Decision**: Use Docker Sandboxes MicroVM (Docker Desktop 4.60+) for team isolation.
Each team gets a dedicated VM with its own kernel.
**Consequences**: Requires Docker Desktop 4.60+. ~2s cold start per sandbox.
Cannot use Docker-in-Docker inside sandbox (but MicroVM supports it natively).

## ADR-002: Redis Streams for Event Bus (Not Kafka)
**Date**: 2026-03-31
**Status**: Accepted
**Context**: Need a persistent, replayable event bus. Kafka is overkill for our
scale (10-50 concurrent agents, ~1000 events/minute). Redis already in stack for cache.
**Decision**: Use Redis Streams for the event bus. Consumer groups for each service.
**Consequences**: Simpler ops (no Kafka cluster). Limited to single-node throughput.
If we need multi-node, migrate to Redis Cluster or Kafka later.

## ADR-003: Bradley-Terry over Classic ELO
**Date**: 2026-03-31
**Status**: Accepted
**Context**: Classic ELO is designed for online, incremental updates (chess players
who improve over time). Our agent configs are static — they don't learn between matches.
**Decision**: Use Bradley-Terry MLE with bootstrap CI, same as LMSYS Chatbot Arena.
Recompute all ratings from full match history after each tournament.
**Consequences**: Slightly more compute per update. But ratings are more stable,
and we get confidence intervals for free.

## ADR-004: Monorepo with Python Packages (Not Microservices)
**Date**: 2026-03-31
**Status**: Accepted
**Context**: Early stage. Need fast iteration. Microservices add network complexity.
**Decision**: Monorepo with Python packages sharing a single FastAPI process.
Each package has clear boundaries (own CLAUDE.md, tests, types).
**Consequences**: Can split into microservices later if needed. Must enforce
package boundaries via import rules (see Rule 01).

## ADR-005: LiteLLM Proxy for Model-Agnostic Agent System
**Date**: 2026-03-31
**Status**: Accepted
**Context**: Need to support multiple LLM providers (Claude, GPT, Gemini, Qwen).
Don't want provider-specific code in agent logic.
**Decision**: All LLM calls go through LiteLLM proxy. Agents specify model names,
LiteLLM routes to the right provider.
**Consequences**: Single point of failure (LiteLLM proxy). Adds ~50ms latency.
But massive simplification of agent code and cost tracking.

## ADR-006: Langfuse for Tracing (Not OpenTelemetry Directly)
**Date**: 2026-03-31
**Status**: Accepted
**Context**: Need LLM-specific observability: token counts, cost tracking, prompt
versioning, evaluation traces. OpenTelemetry is generic.
**Decision**: Use Langfuse for all LLM tracing. Use its Python SDK directly.
**Consequences**: Langfuse-specific dependency. But much richer LLM observability
than raw OpenTelemetry spans.

## ADR-007: JSON Mailbox for Agent Communication (MVP)
**Date**: 2026-03-31
**Status**: Accepted (MVP), Plan to migrate to Redis Lists
**Context**: Need a simple, debuggable communication protocol between agents.
**Decision**: JSON files in team workspace as mailboxes (MVP). Migrate to Redis
lists for production (see Gotcha G010 about file locking).
**Consequences**: Easy to debug (just read the JSON files). But file locking is
fragile under concurrent access. Redis migration planned for Phase 2.

## ADR-008: Claude Code CLI as Agent Runtime
**Date**: 2026-03-31
**Status**: Accepted
**Context**: Need an agent runtime that supports tool use, file operations,
code execution, and self-configuration. Building a custom framework is high effort.
**Decision**: Each team gets its own Claude Code CLI instance running inside their
Docker MicroVM sandbox. Claude Code handles tool execution, file management,
and agentic loops natively. No custom agent framework needed.
**Consequences**: Tight coupling to Claude Code. But eliminates need for custom
tool execution, context management, and agentic loop infrastructure. Teams can
self-bootstrap CLAUDE.md, rules, hooks, and skills naturally.
