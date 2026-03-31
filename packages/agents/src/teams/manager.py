"""
AgentForge Arena — Agent Team Manager

Manages agent team lifecycle: spawning, health checks, communication, teardown.
Each agent is an independent process with role-specific system prompts and tools.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import orjson

from packages.shared.src.config import get_settings
from packages.shared.src.events.bus import EventBus
from packages.shared.src.types.models import (
    Agent,
    AgentMessage,
    AgentRole,
    AgentStatus,
    ModelProvider,
    TeamConfig,
)

logger = logging.getLogger(__name__)

# Agent role → system prompt file mapping
AGENT_PROMPT_FILES: dict[AgentRole, str] = {
    AgentRole.ARCHITECT: ".claude/agents/architect.md",
    AgentRole.BUILDER: ".claude/agents/builder.md",
    AgentRole.FRONTEND: ".claude/agents/frontend.md",
    AgentRole.TESTER: ".claude/agents/tester.md",
    AgentRole.CRITIC: ".claude/agents/critic.md",
    AgentRole.RESEARCHER: ".claude/agents/researcher.md",
}


class AgentProcess:
    """Represents a running agent process."""

    def __init__(
        self,
        agent: Agent,
        system_prompt: str,
        workspace_path: str,
        inbox_path: str,
    ) -> None:
        self.agent = agent
        self.system_prompt = system_prompt
        self.workspace_path = workspace_path
        self.inbox_path = inbox_path
        self._process: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the agent process."""
        self.agent.status = AgentStatus.ACTIVE
        self.agent.last_heartbeat = datetime.utcnow()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Agent %s (%s) started", self.agent.role.value, self.agent.id)

    async def _run_loop(self) -> None:
        """Main agent loop: check inbox, process messages, execute tasks."""
        while self.agent.status not in (AgentStatus.TERMINATED, AgentStatus.ERROR):
            try:
                # Check for new messages
                messages = await self._read_inbox()
                for msg in messages:
                    await self._process_message(msg)

                # Update heartbeat
                self.agent.last_heartbeat = datetime.utcnow()

                # Brief pause between inbox checks
                await asyncio.sleep(2)

            except asyncio.CancelledError:
                self.agent.status = AgentStatus.TERMINATED
                break
            except Exception:
                self.agent.errors_count += 1
                logger.exception("Agent %s error", self.agent.role.value)
                if self.agent.errors_count >= 10:
                    self.agent.status = AgentStatus.ERROR
                    break
                await asyncio.sleep(5)

    async def _read_inbox(self) -> list[AgentMessage]:
        """Read unread messages from the agent's inbox."""
        inbox_file = Path(self.inbox_path) / f"{self.agent.role.value}.json"
        if not inbox_file.exists():
            return []

        try:
            data = orjson.loads(inbox_file.read_bytes())
            messages = [AgentMessage.model_validate(m) for m in data if not m.get("read", False)]
            return messages
        except Exception:
            logger.exception("Failed to read inbox for %s", self.agent.role.value)
            return []

    async def _process_message(self, message: AgentMessage) -> None:
        """Process a single message from the inbox."""
        logger.info(
            "Agent %s processing %s from %s",
            self.agent.role.value,
            message.message_type.value,
            message.from_agent.value,
        )
        self.agent.actions_count += 1

        # Mark as read
        await self._mark_read(message.id)

        # TODO: Route to LLM with system prompt + message context
        # This is where the actual Claude/GPT/etc. call happens via LiteLLM

    async def _mark_read(self, message_id: UUID) -> None:
        """Mark a message as read in the inbox."""
        inbox_file = Path(self.inbox_path) / f"{self.agent.role.value}.json"
        if not inbox_file.exists():
            return

        data = orjson.loads(inbox_file.read_bytes())
        for msg in data:
            if msg.get("id") == str(message_id):
                msg["read"] = True
        inbox_file.write_bytes(orjson.dumps(data))

    async def send_message(self, message: AgentMessage) -> None:
        """Send a message to another agent's inbox."""
        if message.to_agent is None:
            # Broadcast to all agents in the team
            target_roles = [r for r in AgentRole if r != self.agent.role]
        else:
            target_roles = [message.to_agent]

        for role in target_roles:
            inbox_file = Path(self.inbox_path) / f"{role.value}.json"
            existing = []
            if inbox_file.exists():
                existing = orjson.loads(inbox_file.read_bytes())
            existing.append(message.model_dump(mode="json"))
            inbox_file.write_bytes(orjson.dumps(existing))

    async def stop(self) -> None:
        """Stop the agent process."""
        self.agent.status = AgentStatus.TERMINATED
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    @property
    def is_responsive(self) -> bool:
        """Check if agent has sent a heartbeat recently."""
        if self.agent.last_heartbeat is None:
            return False
        elapsed = (datetime.utcnow() - self.agent.last_heartbeat).total_seconds()
        return elapsed < 60


class AgentTeamManager:
    """Manages all agent teams across tournaments."""

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus
        self._teams: dict[UUID, list[AgentProcess]] = {}

    async def spawn_team(
        self,
        team_id: UUID,
        tournament_id: UUID,
        config: TeamConfig,
        sandbox_id: str,
    ) -> list[UUID]:
        """Spawn all agents for a team. Returns list of agent IDs."""
        settings = get_settings()
        workspace_path = f"{settings.sandbox.workspace_base}/team-{team_id}/project"
        inbox_path = f"{settings.sandbox.workspace_base}/team-{team_id}/inbox"

        agents: list[AgentProcess] = []
        agent_ids: list[UUID] = []

        for agent_config in config.agents:
            agent = Agent(
                id=uuid4(),
                team_id=team_id,
                tournament_id=tournament_id,
                role=agent_config.role,
                model=agent_config.model,
            )

            # Load system prompt
            prompt_file = AGENT_PROMPT_FILES.get(agent_config.role, "")
            system_prompt = ""
            try:
                system_prompt = Path(prompt_file).read_text()
            except FileNotFoundError:
                logger.warning("System prompt not found: %s", prompt_file)
                system_prompt = f"You are the {agent_config.role.value} agent."

            process = AgentProcess(
                agent=agent,
                system_prompt=system_prompt,
                workspace_path=workspace_path,
                inbox_path=inbox_path,
            )

            await process.start()
            agents.append(process)
            agent_ids.append(agent.id)

        self._teams[team_id] = agents
        logger.info("Spawned %d agents for team %s", len(agents), team_id)
        return agent_ids

    async def check_team_health(self, team_id: UUID) -> dict:
        """Check health of all agents in a team."""
        agents = self._teams.get(team_id, [])
        if not agents:
            return {"all_responsive": False, "error": "Team not found"}

        unresponsive = []
        for ap in agents:
            if not ap.is_responsive:
                unresponsive.append({
                    "role": ap.agent.role.value,
                    "agent_id": str(ap.agent.id),
                    "last_heartbeat": (
                        ap.agent.last_heartbeat.isoformat()
                        if ap.agent.last_heartbeat
                        else None
                    ),
                    "errors": ap.agent.errors_count,
                })

        return {
            "all_responsive": len(unresponsive) == 0,
            "total_agents": len(agents),
            "responsive": len(agents) - len(unresponsive),
            "unresponsive": unresponsive,
        }

    async def get_team_agents(self, team_id: UUID) -> list[Agent]:
        """Get all agent metadata for a team."""
        agents = self._teams.get(team_id, [])
        return [ap.agent for ap in agents]

    async def teardown_team(self, team_id: UUID) -> None:
        """Stop all agents in a team."""
        agents = self._teams.get(team_id, [])
        for ap in agents:
            await ap.stop()
        if team_id in self._teams:
            del self._teams[team_id]
        logger.info("Team %s torn down", team_id)

    async def teardown_all(self) -> None:
        """Teardown all teams. Used in shutdown."""
        team_ids = list(self._teams.keys())
        for team_id in team_ids:
            await self.teardown_team(team_id)
