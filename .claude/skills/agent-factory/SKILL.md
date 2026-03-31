---
name: agent-factory
description: |
  Create, configure, and spawn agent teams with role-specific system prompts,
  tool permissions, and communication channels. Use when setting up new agent
  teams, modifying agent configurations, or debugging agent behavior. Triggers
  on: "spawn agent", "create team", "configure agent", "agent setup",
  "agent permissions", or when the Orchestrator initializes a tournament.
---

# Agent Factory Skill

## Purpose
Produce fully configured, ready-to-compete agent teams from a team configuration spec.

## Team Configuration Spec
```python
from pydantic import BaseModel
from enum import Enum

class ModelChoice(str, Enum):
    OPUS_4_6 = "claude-opus-4-6"
    SONNET_4_6 = "claude-sonnet-4-6"
    HAIKU_4_5 = "claude-haiku-4-5"
    GPT_5 = "gpt-5"
    GEMINI_3_PRO = "gemini-3-pro"
    QWEN3_72B = "qwen3-72b"

class AgentRoleConfig(BaseModel):
    role: str                        # architect, builder, frontend, tester, critic
    model: ModelChoice
    system_prompt_path: str          # Path to .claude/agents/{role}.md
    tools: list[str]                 # Allowed tool patterns
    max_tokens_per_action: int = 8192
    temperature: float = 0.3
    timeout_seconds: int = 300

class TeamConfig(BaseModel):
    team_id: str
    name: str
    agents: list[AgentRoleConfig]
    strategy: dict                   # Mutable strategy parameters
    sandbox_memory: str = "4g"
    sandbox_cpus: int = 2
```

## Preset Configurations

### `all-opus`
```python
TeamConfig(agents=[
    AgentRoleConfig(role="architect", model="claude-opus-4-6"),
    AgentRoleConfig(role="builder", model="claude-opus-4-6"),
    AgentRoleConfig(role="frontend", model="claude-opus-4-6"),
    AgentRoleConfig(role="tester", model="claude-opus-4-6"),
    AgentRoleConfig(role="critic", model="claude-opus-4-6"),
])
```

### `balanced` (Recommended)
```python
TeamConfig(agents=[
    AgentRoleConfig(role="architect", model="claude-opus-4-6"),
    AgentRoleConfig(role="builder", model="claude-sonnet-4-6"),
    AgentRoleConfig(role="frontend", model="claude-sonnet-4-6"),
    AgentRoleConfig(role="tester", model="claude-haiku-4-5"),
    AgentRoleConfig(role="critic", model="claude-opus-4-6"),
])
```

## Spawn Sequence
1. **Validate config** — All required fields, valid model choices
2. **Create workspace** — `/arena/team-{id}/` with proper directory structure
3. **Initialize mailboxes** — JSON files for inter-agent communication
4. **Load system prompts** — Read from `.claude/agents/` and inject context
5. **Configure LiteLLM routing** — Set up model routing per agent role
6. **Start agent processes** — Each agent as an independent process
7. **Health check** — Verify each agent responds within 10s
8. **Register with orchestrator** — Publish `tournament.team.spawned`

## Self-Configuration After Spawn
Once spawned, the Architect agent can create additional config:
- Project-specific CLAUDE.md
- Custom `.claude/rules/` for the project
- Custom `.claude/skills/` if the challenge needs them
- Custom `.claude/hooks/` for the project's stack
- Sub-agent definitions for specialized tasks

This is the "agents creating their own agent configs" capability.
The Architect designs the project structure and the agent workflow simultaneously.
