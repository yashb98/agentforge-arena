# /tournament-start

Start a new tournament with the specified configuration.

## Usage
```
/tournament-start [format] [challenge_id]
```

## Arguments
- `format`: `duel` (default) | `standard` | `league` | `grand_prix`
- `challenge_id`: ID from the challenge library (optional — random if omitted)

## What This Command Does

1. **Validate Configuration**
   - Check available resources (Docker, Redis, PostgreSQL)
   - Verify LLM API keys are configured
   - Check budget availability
   - Verify challenge exists and is valid

2. **Create Tournament Record**
   - Generate tournament ID
   - Create database record with config
   - Set initial phase to `PREP`

3. **Provision Sandboxes**
   - Create Docker Sandbox MicroVM per team
   - Configure network allow/deny lists
   - Set resource limits (RAM, CPU, disk)
   - Initialize git repos in each sandbox

4. **Spawn Agent Teams**
   - Initialize agent processes per team
   - Load agent system prompts from `.claude/agents/`
   - Set up JSON mailbox directories
   - Verify all agents are responsive (health check)

5. **Deliver Challenge**
   - Copy challenge brief to each team's sandbox
   - Start phase timer
   - Publish `tournament.started` event
   - Begin spectator streaming

## Example
```bash
# Start a duel with random challenge
/tournament-start duel

# Start a 4-team standard tournament with specific challenge
/tournament-start standard challenge_url_shortener

# Start a league with 6 teams
/tournament-start league
```

## Execution Steps
```python
from packages.core.src.tournament.orchestrator import TournamentOrchestrator
from packages.core.src.tournament.config import TournamentConfig

config = TournamentConfig(
    format="$FORMAT",
    challenge_id="$CHALLENGE_ID",
    team_count={"duel": 2, "standard": 4, "league": 6, "grand_prix": 8}["$FORMAT"],
    agents_per_team=5,
)

orchestrator = TournamentOrchestrator()
tournament = await orchestrator.start(config)
print(f"Tournament {tournament.id} started — Phase: {tournament.current_phase}")
```
