# /agent-spawn

Spawn a new agent team for a tournament.

## Usage
```
/agent-spawn [team_id] [config_name]
```

## Config Options
- `all-opus` — All 5 agents use Opus 4.6 ($200-400 per match)
- `balanced` — Opus for Architect+Critic, Sonnet for Builder+Frontend, Haiku for Tester ($100-200)
- `budget` — Sonnet for lead roles, Haiku for support ($50-100)
- `mixed` — Multi-provider: Opus Architect, GPT-5 Builder, Gemini Frontend ($150-250)
- `open-source` — Qwen3 variants across all roles ($20-40)

## Steps
1. Create team workspace in sandbox
2. Initialize JSON mailbox directories
3. Spawn each agent process with role-specific system prompt
4. Health check all 5 agents
5. Publish `tournament.team.spawned` event

---

# /sandbox-create

Create an isolated Docker Sandbox MicroVM for a tournament team.

## Usage
```
/sandbox-create [team_id] [memory] [cpus]
```

## Defaults
- memory: `4g`
- cpus: `2`

## Steps
```bash
docker sandbox create claude ~/arena/team-$TEAM_ID \
  --network-allow "pypi.org,registry.npmjs.org,api.anthropic.com,github.com" \
  --network-deny "*" \
  --memory $MEMORY \
  --cpus $CPUS
```

---

# /judge-run

Run the judging pipeline on tournament submissions.

## Usage
```
/judge-run [tournament_id]
```

## Judging Pipeline
1. **Automated Judges** (parallel)
   - `pytest` — Run hidden test suite against each team's code
   - `ruff + mypy` — Code quality scoring
   - `coverage.py` — Test coverage measurement
2. **LLM Judge** (sequential)
   - Opus 4.6 reviews UX/Design (screenshot evaluation)
   - Opus 4.6 reviews Architecture (ARCHITECTURE.md + code structure)
   - Opus 4.6 reviews Innovation (novel approaches)
3. **Score Calculation**
   - Weighted composite: Functionality 30%, Quality 20%, Coverage 15%, UX 15%, Architecture 10%, Innovation 10%
4. **ELO Update**
   - Bradley-Terry model update with new match result
5. **Publish Results**
   - `tournament.match.judged` event with full scores

---

# /health-check

Verify all platform services are operational.

## Usage
```
/health-check
```

## Checks
1. **PostgreSQL** — Connection test, migration status
2. **Redis** — Ping, memory usage, pub/sub test
3. **Docker** — Daemon running, sandbox support available
4. **MinIO** — Connection test, bucket exists
5. **Langfuse** — API reachable, project configured
6. **LiteLLM** — Proxy running, models accessible
7. **Agent System** — Inbox directories exist, permissions correct

## Output
```
✅ PostgreSQL    — Connected, 3 pending migrations
✅ Redis         — Connected, 45MB used, pub/sub active
✅ Docker        — Running, sandbox support: yes
✅ MinIO         — Connected, bucket 'arena-artifacts' exists
⚠️  Langfuse     — Connected, but trace queue depth: 1,247 (high)
✅ LiteLLM       — Proxy at :4000, 3 models configured
✅ Agent System  — Inbox dirs OK, permissions OK
```
