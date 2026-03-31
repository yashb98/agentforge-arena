---
name: tournament-engine
description: |
  Manage tournament lifecycle phases, timing, and coordination. Use when working
  on tournament orchestration, phase transitions, or timing logic. Triggers on:
  "tournament", "phase", "match", "duel", "bracket", or orchestration work.
---

# Tournament Engine Skill

## Phase State Machine
```
PREP → RESEARCH → ARCHITECTURE → BUILD → CROSS_REVIEW → FIX → JUDGE → COMPLETE
  ↓                                                                      ↓
CANCELLED ←←←←←←←←←←←←←← (any phase can cancel) ←←←←←←←←←←←←←←←←←←←←
```

## Phase Timing (Configurable)
| Phase | Duel | Standard | League | Grand Prix |
|-------|------|----------|--------|------------|
| PREP | 5m | 5m | 10m | 10m |
| RESEARCH | 30m | 30m | 30m | 20m |
| ARCHITECTURE | 15m | 15m | 15m | 10m |
| BUILD | 90m | 75m | 60m | 45m |
| CROSS_REVIEW | 15m | 15m | 10m | 10m |
| FIX | 15m | 15m | 10m | 10m |
| JUDGE | 10m | 15m | 20m | 15m |

## Phase Transition Protocol
1. Check all agents have saved their work (git commit)
2. Publish `tournament.phase.ending` warning (60s before)
3. Wait for confirmation or force after timeout
4. Publish `tournament.phase.changed` event
5. Update database record
6. Notify all agents via mailbox
7. Update spectator dashboard
8. Start next phase timer

## Bracket Formats
- **Duel**: 1 match, direct comparison
- **Standard**: Single elimination bracket (4 teams → 2 semifinals → 1 final)
- **League**: Round-robin (every team plays every other team)
- **Grand Prix**: Swiss system (8 teams, 3-4 rounds, pairings by score)
