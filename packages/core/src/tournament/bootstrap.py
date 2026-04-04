"""Wire the same services as FastAPI lifespan — for CLI and headless tournament runs."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

import redis.asyncio as aioredis

from packages.shared.src.config import get_settings
from packages.shared.src.db.base import close_db, init_db
from packages.shared.src.events.bus import EventBus

logger = logging.getLogger(__name__)


@dataclass
class TournamentRuntimeStack:
    """Live references for create/start/cancel; call ``aclose`` when done."""

    redis: aioredis.Redis
    event_bus: EventBus
    orchestrator: object
    agent_manager: object
    sandbox_manager: object
    llm_client: object
    langfuse: object | None = None

    async def aclose(self) -> None:
        if hasattr(self.agent_manager, "teardown_all"):
            await self.agent_manager.teardown_all()  # type: ignore[union-attr]
        if hasattr(self.sandbox_manager, "destroy_all"):
            await self.sandbox_manager.destroy_all()  # type: ignore[union-attr]
        if hasattr(self.llm_client, "close"):
            await self.llm_client.close()  # type: ignore[union-attr]
        if self.langfuse is not None and hasattr(self.langfuse, "flush"):
            self.langfuse.flush()
        await self.redis.close()
        await close_db()


@asynccontextmanager
async def tournament_runtime_stack() -> AsyncIterator[TournamentRuntimeStack]:
    """Initialize DB, Redis, bus, LLM, sandbox, agents, orchestrator (matches ``main.lifespan``)."""
    settings = get_settings()
    await init_db()
    logger.info("Database initialized (CLI bootstrap)")

    redis_client = aioredis.from_url(settings.redis.url, decode_responses=False)
    await redis_client.ping()

    event_bus = EventBus(redis_client)

    langfuse = None
    if settings.langfuse.enabled:
        try:
            from langfuse import Langfuse

            langfuse = Langfuse(
                public_key=settings.langfuse.public_key,
                secret_key=settings.langfuse.secret_key.get_secret_value(),
                host=settings.langfuse.host,
            )
        except Exception:
            logger.warning("Langfuse init failed — tracing disabled for CLI run")

    from packages.shared.src.llm.client import LLMClient

    llm_client = LLMClient(langfuse=langfuse)

    from packages.sandbox.src.docker.manager import SandboxManager

    sandbox_manager = SandboxManager()

    from packages.agents.src.teams.manager import AgentTeamManager

    agent_manager = AgentTeamManager(
        event_bus=event_bus,
        redis=redis_client,
        llm_client=llm_client,
    )

    from packages.judge.src.scoring.service import JudgeService

    judge_service = JudgeService(
        event_bus=event_bus,
        sandbox_manager=sandbox_manager,
        llm_client=llm_client,
    )

    from packages.core.src.tournament.orchestrator import TournamentOrchestrator

    orchestrator = TournamentOrchestrator(
        event_bus=event_bus,
        sandbox_manager=sandbox_manager,
        agent_manager=agent_manager,
        judge_service=judge_service,
    )

    try:
        await orchestrator.restore_durable_tournaments()
    except Exception:
        logger.exception("restore_durable_tournaments failed — continuing")

    stack = TournamentRuntimeStack(
        redis=redis_client,
        event_bus=event_bus,
        orchestrator=orchestrator,
        agent_manager=agent_manager,
        sandbox_manager=sandbox_manager,
        llm_client=llm_client,
        langfuse=langfuse,
    )

    try:
        yield stack
    finally:
        await stack.aclose()
