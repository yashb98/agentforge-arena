# packages/core — CLAUDE.md

## What This Package Is
The tournament orchestration engine. Manages the full lifecycle:
tournament creation → phase transitions → timing → completion.

## Key Modules
- `src/tournament/cli.py` — Headless `start` command (`python -m packages.core.src.tournament.cli` / `arena-tournament`)
- `src/tournament/bootstrap.py` — Wires Redis, bus, LLM, sandbox, agents, orchestrator (mirrors API lifespan)
- `src/tournament/defaults.py` — Default team rosters per `TournamentFormat`
- `src/tournament/orchestrator.py` — Main orchestrator (phase state machine)
- `src/tournament/phases.py` — Phase-specific logic (research, build, judge, etc.)
- `src/tournament/timer.py` — Phase timing and deadline enforcement
- `src/challenge/library.py` — Challenge selection and management
- `src/challenge/generator.py` — Dynamic challenge generation
- `src/elo/calculator.py` — Bradley-Terry ELO implementation
- `src/elo/leaderboard.py` — Leaderboard queries and rankings
- `src/config/presets.py` — Team configuration presets

## Dependencies
- `packages/shared` — Types, DB, events, config
- `packages/sandbox` — Sandbox creation/teardown
- `packages/agents` — Agent team spawning

## Rules
- Phase transitions MUST publish events
- Timing enforcement is strict — phases end on deadline; `tournament.phase.tick` + `tournament.team.clock_tick` fire about every 5 minutes with `seconds_remaining` (hackathon pressure)
- Phase start team notifications include `phase_deadline_utc`, `seconds_remaining`, and research-before-implementation copy where relevant
- The orchestrator does NOT write code — it coordinates
