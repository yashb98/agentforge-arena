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
    """Get the shared event bus instance from app state.

    The EventBus is initialised during lifespan startup and stored at
    request.app.state.event_bus. Route handlers should use this via Depends().

    Example:
        @router.get("/example")
        async def my_route(bus: EventBus = Depends(get_event_bus)):
            await bus.publish("example.event", payload={...})
    """
    return request.app.state.event_bus  # type: ignore[no-any-return]


def get_orchestrator(request: Request):  # type: ignore[return]  # noqa: ANN201
    """Get the tournament orchestrator instance from app state.

    The orchestrator is initialised during lifespan startup and stored at
    request.app.state.orchestrator. Route handlers should use this via Depends().

    Returns the concrete orchestrator type (imported lazily to avoid circular
    imports at module load time).

    Example:
        @router.post("/tournaments")
        async def create(orch = Depends(get_orchestrator)):
            return await orch.create(config)
    """
    return request.app.state.orchestrator


def get_agent_manager(request: Request):  # type: ignore[return]  # noqa: ANN201
    """Get the agent team manager instance from app state.

    The agent manager is initialised during lifespan startup and stored at
    request.app.state.agent_manager. Route handlers should use this via Depends().

    Example:
        @router.get("/tournaments/{tid}/agents")
        async def list_agents(mgr = Depends(get_agent_manager)):
            return await mgr.list_teams(tid)
    """
    return request.app.state.agent_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session with automatic commit/rollback.

    Opens a session via the shared get_session() async context manager.
    Commits on success, rolls back on any exception (handled inside
    get_session), and always closes the session on exit.

    Use with FastAPI Depends():
        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db_session)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    async with get_session() as session:
        yield session
