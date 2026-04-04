# packages/agents — CLAUDE.md

## What This Package Is
Agent team lifecycle management. Spawns agents, manages communication,
handles self-configuration, and monitors health.

## Key Modules
- `src/teams/manager.py` — AgentTeamManager: spawn, health check, teardown
- `src/roles/` — Role-specific behavior (how each role processes tasks)
- `src/communication/mailbox.py` — JSON mailbox protocol implementation
- `src/communication/redis_mailbox.py` — Redis-based mailbox (production)
- `src/strategies/` — Agent strategy configs (research-first, build-fast, etc.)
- `src/spawner/process.py` — Agent process management
- `src/self_config/bootstrap.py` — Agent self-configuration (creating CLAUDE.md, rules, hooks)

## The Self-Configuration Flow
When an Architect agent starts a project, it can:
1. Create a project-specific CLAUDE.md
2. Define `.claude/rules/` for the project's stack
3. Create `.claude/skills/` if needed
4. Set up `.claude/hooks/` for auto-formatting
5. Search for and configure MCP plugins

This is the "agents creating their own agent configs" capability. In tournaments, **all of the above lives under the team sandbox project root** (`…/team-{id}/project/`). The Arena monorepo is not the editable workspace for competing agents.

## Dependencies
- `packages/shared` — Types, events, config
