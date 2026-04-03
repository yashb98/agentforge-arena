"""
AgentForge Arena — Agent Team Manager

Manages agent team lifecycle: spawning, health checks, communication, teardown.
Each agent is an independent process with role-specific system prompts and tools.
Communication between agents uses Redis-backed mailboxes (atomic LPUSH/BRPOP).
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid4

from packages.agents.src.communication.mailbox import RedisMailbox
from packages.shared.src.config import get_settings
from packages.shared.src.types.models import (
    Agent,
    AgentMessage,
    AgentRole,
    AgentStatus,
    TeamConfig,
)

if TYPE_CHECKING:
    import redis.asyncio as aioredis

    from packages.shared.src.events.bus import EventBus

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


class MemoryManagerProtocol(Protocol):
    """Minimal memory hooks used by agent runtime."""

    async def recall(self, agent_id: UUID, role: AgentRole, query: str) -> dict:
        ...

    async def record(
        self,
        agent_id: UUID,
        role: AgentRole,
        *,
        task: str | None = None,
        decision: str | None = None,
        notes: list[str] | None = None,
        metadata: dict | None = None,
    ) -> None:
        ...


class AgentProcess:
    """Represents a running agent process with Redis-backed communication."""

    def __init__(
        self,
        agent: Agent,
        system_prompt: str,
        workspace_path: str,
        mailbox: RedisMailbox,
        llm_client: object | None = None,
        memory_manager: MemoryManagerProtocol | None = None,
    ) -> None:
        self.agent = agent
        self.system_prompt = system_prompt
        self.workspace_path = workspace_path
        self._mailbox = mailbox
        self._llm_client = llm_client
        self._memory_manager = memory_manager
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the agent process."""
        self.agent.status = AgentStatus.ACTIVE
        self.agent.last_heartbeat = datetime.utcnow()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Agent %s (%s) started", self.agent.role.value, self.agent.id)

    async def _run_loop(self) -> None:
        """Main agent loop: wait for messages via Redis BRPOP, process them."""
        while self.agent.status not in (AgentStatus.TERMINATED, AgentStatus.ERROR):
            try:
                # Blocking wait for next message (5s timeout for heartbeat updates)
                message = await self._mailbox.receive(self.agent.role, timeout=5.0)

                if message is not None:
                    await self._process_message(message)

                # Update heartbeat regardless
                self.agent.last_heartbeat = datetime.utcnow()

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
        """Read all pending messages from Redis mailbox (non-blocking)."""
        return await self._mailbox.receive_all(self.agent.role)

    async def _process_message(self, message: AgentMessage) -> None:
        """Process a single message from the inbox via LLM."""
        logger.info(
            "Agent %s processing %s from %s",
            self.agent.role.value,
            message.message_type.value,
            message.from_agent.value,
        )
        self.agent.actions_count += 1

        if self._llm_client is None:
            logger.warning("Agent %s has no LLM client — skipping LLM call", self.agent.role.value)
            return

        # Build conversation for LLM
        memory_context: dict | None = None
        if self._memory_manager is not None:
            try:
                memory_context = await self._memory_manager.recall(
                    self.agent.id,
                    self.agent.role,
                    query=f"{message.message_type.value}:{json.dumps(message.payload)}",
                )
            except Exception:
                logger.exception("Memory recall failed for agent %s", self.agent.id)

        user_content = (
            f"[{message.message_type.value}] from {message.from_agent.value}:\n"
            f"{json.dumps(message.payload)}"
        )
        if memory_context:
            user_content += f"\n\n[MEMORY]\n{json.dumps(memory_context)}"

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            response = await self._llm_client.completion(  # type: ignore[union-attr]
                messages=messages,
                model=self.agent.model,
                trace_name=f"agent.{self.agent.role.value}.{message.message_type.value}",
                trace_metadata={
                    "agent_id": str(self.agent.id),
                    "team_id": str(self.agent.team_id),
                    "message_type": message.message_type.value,
                },
            )

            # Track token usage
            self.agent.total_tokens_used += response.usage.total_tokens
            self.agent.total_cost_usd += response.usage.cost_usd

            logger.debug(
                "Agent %s LLM response: %d tokens, $%.4f",
                self.agent.role.value,
                response.usage.total_tokens,
                response.usage.cost_usd,
            )

            if self._memory_manager is not None:
                try:
                    module_name = None
                    if isinstance(message.payload, dict):
                        module_name_raw = message.payload.get("module_name")
                        if isinstance(module_name_raw, str):
                            module_name = module_name_raw
                    await self._memory_manager.record(
                        self.agent.id,
                        self.agent.role,
                        task=f"{message.message_type.value} from {message.from_agent.value}",
                        decision=getattr(response, "content", "")[:500],
                        metadata={
                            "team_id": str(self.agent.team_id),
                            "module_name": module_name or "general",
                            "message_type": message.message_type.value,
                        },
                    )
                except Exception:
                    logger.exception("Memory record failed for agent %s", self.agent.id)

        except Exception:
            self.agent.errors_count += 1
            logger.exception("Agent %s LLM call failed", self.agent.role.value)

    async def send_message(self, message: AgentMessage) -> None:
        """Send a message via Redis mailbox."""
        await self._mailbox.send(message)

    async def stop(self) -> None:
        """Stop the agent process."""
        self.agent.status = AgentStatus.TERMINATED
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    @property
    def is_responsive(self) -> bool:
        """Check if agent has sent a heartbeat recently."""
        if self.agent.last_heartbeat is None:
            return False
        elapsed = (datetime.utcnow() - self.agent.last_heartbeat).total_seconds()
        return elapsed < 60


class AgentTeamManager:
    """Manages all agent teams across tournaments."""

    def __init__(
        self,
        event_bus: EventBus,
        redis: aioredis.Redis | None = None,
        llm_client: object | None = None,
        memory_manager: MemoryManagerProtocol | None = None,
    ) -> None:
        self._events = event_bus
        self._redis = redis
        self._llm_client = llm_client
        self._memory_manager = memory_manager
        self._teams: dict[UUID, list[AgentProcess]] = {}
        self._mailboxes: dict[UUID, RedisMailbox] = {}
        self._hierarchy_by_tournament: dict[UUID, dict[UUID, list[UUID]]] = {}

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

        # Create shared Redis mailbox for this team
        if self._redis is None:
            raise RuntimeError("Redis not configured — cannot create agent mailbox")
        mailbox = RedisMailbox(redis=self._redis, team_id=team_id)

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
                mailbox=mailbox,
                llm_client=self._llm_client,
                memory_manager=self._memory_manager,
            )

            await process.start()
            agents.append(process)
            agent_ids.append(agent.id)

        self._teams[team_id] = agents
        self._mailboxes[team_id] = mailbox
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
        """Stop all agents and clean up Redis mailboxes."""
        agents = self._teams.get(team_id, [])
        for ap in agents:
            await ap.stop()

        # Clear Redis mailboxes
        mailbox = self._mailboxes.get(team_id)
        if mailbox:
            await mailbox.clear_team()
            del self._mailboxes[team_id]

        if team_id in self._teams:
            del self._teams[team_id]
        logger.info("Team %s torn down (agents + mailboxes)", team_id)

    async def teardown_all(self) -> None:
        """Teardown all teams. Used in shutdown."""
        team_ids = list(self._teams.keys())
        for team_id in team_ids:
            await self.teardown_team(team_id)

    async def set_team_hierarchy(
        self,
        *,
        tournament_id: UUID,
        hierarchy: dict[UUID, list[UUID]],
    ) -> None:
        """Register parent->children team mapping for coordination queries."""
        self._hierarchy_by_tournament[tournament_id] = hierarchy

    async def get_hierarchy_health(self, tournament_id: UUID) -> dict[str, dict]:
        """Aggregate health view by parent team for hierarchical setups."""
        hierarchy = self._hierarchy_by_tournament.get(tournament_id, {})
        out: dict[str, dict] = {}
        for parent_id, children in hierarchy.items():
            child_health = []
            for child_id in children:
                child_health.append(await self.check_team_health(child_id))
            out[str(parent_id)] = {
                "children": [str(child_id) for child_id in children],
                "child_health": child_health,
            }
        return out
