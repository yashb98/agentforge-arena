"""
AgentForge Arena — FastAPI Dependency Injection Providers

Central wiring for all shared service instances. Route handlers use these
with FastAPI's Depends() to receive the correct service objects.

All services are stored on app.state during lifespan startup (see main.py).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.src.db.base import get_session
from packages.shared.src.events.bus import EventBus


def get_event_bus(request: Request) -> EventBus:
    """Get the shared event bus instance from app state."""
    return request.app.state.event_bus  # type: ignore[no-any-return]


def get_orchestrator(request: Request) -> "TournamentOrchestrator":
    """Get the tournament orchestrator instance from app state."""
    from packages.core.src.tournament.orchestrator import TournamentOrchestrator

    orchestrator: TournamentOrchestrator = request.app.state.orchestrator
    return orchestrator


def get_agent_manager(request: Request) -> "AgentTeamManager":
    """Get the agent team manager instance from app state."""
    from packages.agents.src.teams.manager import AgentTeamManager

    agent_manager: AgentTeamManager = request.app.state.agent_manager
    return agent_manager


def get_sandbox_manager(request: Request) -> "SandboxManager":
    """Get the sandbox manager instance from app state."""
    from packages.sandbox.src.docker.manager import SandboxManager

    sandbox_manager: SandboxManager = request.app.state.sandbox_manager
    return sandbox_manager


def get_judge_service(request: Request) -> "JudgeService":
    """Get the judge service instance from app state."""
    from packages.judge.src.scoring.service import JudgeService

    judge_service: JudgeService = request.app.state.judge_service
    return judge_service


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session with automatic commit/rollback.

    Opens a session via the shared get_session() async context manager.
    Commits on success, rolls back on any exception (handled inside
    get_session), and always closes the session on exit.
    """
    async with get_session() as session:
        yield session
