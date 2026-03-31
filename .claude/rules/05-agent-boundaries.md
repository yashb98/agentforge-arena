# Rule 05: Agent Boundaries & Self-Configuration

## Applies To
All agent operations within tournament sandboxes and the agent orchestration system.

## Agent Isolation Boundaries

### Filesystem Isolation
- Each team gets a dedicated workspace: `/arena/team-{id}/`
- Agents CANNOT read/write outside their team workspace
- Cross-review phase grants READ-ONLY access to opponent workspace
- Agent-created projects live inside: `/arena/team-{id}/project/`

### Process Isolation
- Each agent runs as a separate process inside the team's MicroVM
- Agents share the MicroVM's filesystem but have role-based permissions
- Only the Architect agent can modify `ARCHITECTURE.md` and `.claude/` config
- Only the Tester agent can run the test suite
- The Critic agent has read-only access + bash for running/testing

### Communication Isolation
- Agents communicate ONLY via JSON mailbox protocol
- No direct function calls between agents
- All messages are logged and traceable
- Message format is strict — see communication protocol below

## Self-Configuration Capabilities

### What Agents CAN Create (Inside Their Sandbox)
```
/arena/team-{id}/project/
├── CLAUDE.md                ← Architect creates this for the project
├── .claude/
│   ├── rules/              ← Architect defines project-specific rules
│   │   └── stack-rules.md  ← e.g., "Use FastAPI, not Flask"
│   ├── skills/             ← Agents can create custom skills
│   │   └── api-builder/
│   │       └── SKILL.md
│   ├── hooks/              ← Auto-formatting, linting hooks
│   │   └── post-write-format.sh
│   └── agents/             ← Sub-agent definitions for complex tasks
│       └── db-specialist.md
├── README.md
├── ARCHITECTURE.md
├── pyproject.toml / package.json
└── src/
```

### What Agents CANNOT Do
- Modify the platform's `.claude/` configuration
- Access other team's sandboxes (except read-only in cross-review)
- Install system-level packages (`apt-get`, `brew`)
- Change network allow/deny lists
- Modify their own system prompts during a tournament
- Access the host machine's filesystem
- Spawn processes outside the sandbox

## Agent Self-Improvement Protocol

Between tournament rounds (not during a match), agents can:

1. **Analyze past performance** — Read Langfuse traces of their own actions
2. **Update strategies** — Modify their strategy config (not system prompt)
3. **Create skills** — Package reusable patterns as skills for future matches
4. **Recommend changes** — Suggest system prompt modifications (human approval required)

### Strategy Config (Mutable Between Rounds)
```json
{
  "research_time_budget_pct": 0.20,
  "test_driven": true,
  "architecture_first": true,
  "parallel_build": true,
  "review_aggressiveness": "high",
  "preferred_stack": {
    "backend": "fastapi",
    "frontend": "nextjs",
    "database": "postgresql",
    "cache": "redis"
  }
}
```

## Communication Protocol

### JSON Mailbox Format
```json
{
  "from": "architect",
  "to": "builder",
  "type": "task_assignment",
  "priority": "high",
  "timestamp": "2026-03-31T10:15:00.000Z",
  "correlation_id": "match-abc-task-001",
  "payload": {
    "task_id": "build-api-routes",
    "description": "Implement REST API routes per ARCHITECTURE.md",
    "files_to_create": ["src/api/routes.py", "src/api/models.py"],
    "dependencies": ["build-db-models"],
    "deadline_phase": "BUILD_SPRINT",
    "acceptance_criteria": [
      "All CRUD endpoints for core entities",
      "Pydantic request/response models",
      "Error handling with proper HTTP status codes",
      "pytest tests with >80% coverage"
    ]
  },
  "read": false
}
```

### Message Types
| Type | From | To | Purpose |
|------|------|----|---------|
| `task_assignment` | Architect | Any | Assign work |
| `task_complete` | Any | Architect | Report completion |
| `review_request` | Any | Critic | Request code review |
| `review_feedback` | Critic | Any | Review results |
| `bug_report` | Tester/Critic | Builder/Frontend | Report issue |
| `architecture_update` | Architect | All | Design change |
| `help_request` | Any | Any | Ask for assistance |
| `status_update` | Any | Architect | Progress report |
| `conflict_resolution` | Architect | Any | Resolve disagreements |

## Plugin Discovery by Agents

Agents can search for and use MCP plugins during the research/build phase:

1. **Search**: Query the MCP registry for relevant tools
2. **Evaluate**: Check stars, last update, compatibility
3. **Install**: Add to project's `.claude/plugins/` with config
4. **Use**: Integrate into their workflow

### Plugin Evaluation Criteria (Automated)
- Last commit < 30 days ago (actively maintained)
- Stars > 50 (community trust)
- Has TypeScript types or Python type hints
- Compatible with the project's stack
- No known security vulnerabilities (check advisories)
