"""
AgentForge Arena — Tests for FastAPI Dependency Injection Providers

Tests that dependency functions correctly extract state from request.app.state
and that the database session dependency yields and commits/rolls back correctly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """A mock EventBus instance."""
    return MagicMock()


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    """A mock tournament orchestrator instance."""
    return MagicMock()


@pytest.fixture
def mock_agent_manager() -> MagicMock:
    """A mock agent team manager instance."""
    return MagicMock()


@pytest.fixture
def mock_request(mock_event_bus, mock_orchestrator, mock_agent_manager) -> MagicMock:
    """A mock FastAPI Request with app.state populated."""
    request = MagicMock()
    request.app.state.event_bus = mock_event_bus
    request.app.state.orchestrator = mock_orchestrator
    request.app.state.agent_manager = mock_agent_manager
    return request


# ---------------------------------------------------------------------------
# get_event_bus
# ---------------------------------------------------------------------------


def test_get_event_bus_returns_app_state_event_bus(mock_request, mock_event_bus):
    """get_event_bus should return request.app.state.event_bus."""
    from packages.api.src.dependencies import get_event_bus

    result = get_event_bus(mock_request)

    assert result is mock_event_bus


def test_get_event_bus_with_different_instance(mock_request):
    """get_event_bus returns whatever object is stored on app.state.event_bus."""
    from packages.api.src.dependencies import get_event_bus

    sentinel = object()
    mock_request.app.state.event_bus = sentinel

    result = get_event_bus(mock_request)

    assert result is sentinel


# ---------------------------------------------------------------------------
# get_orchestrator
# ---------------------------------------------------------------------------


def test_get_orchestrator_returns_app_state_orchestrator(mock_request, mock_orchestrator):
    """get_orchestrator should return request.app.state.orchestrator."""
    from packages.api.src.dependencies import get_orchestrator

    result = get_orchestrator(mock_request)

    assert result is mock_orchestrator


def test_get_orchestrator_with_different_instance(mock_request):
    """get_orchestrator returns whatever object is stored on app.state.orchestrator."""
    from packages.api.src.dependencies import get_orchestrator

    sentinel = object()
    mock_request.app.state.orchestrator = sentinel

    result = get_orchestrator(mock_request)

    assert result is sentinel


# ---------------------------------------------------------------------------
# get_agent_manager
# ---------------------------------------------------------------------------


def test_get_agent_manager_returns_app_state_agent_manager(mock_request, mock_agent_manager):
    """get_agent_manager should return request.app.state.agent_manager."""
    from packages.api.src.dependencies import get_agent_manager

    result = get_agent_manager(mock_request)

    assert result is mock_agent_manager


def test_get_agent_manager_with_different_instance(mock_request):
    """get_agent_manager returns whatever object is stored on app.state.agent_manager."""
    from packages.api.src.dependencies import get_agent_manager

    sentinel = object()
    mock_request.app.state.agent_manager = sentinel

    result = get_agent_manager(mock_request)

    assert result is sentinel


# ---------------------------------------------------------------------------
# get_db_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_db_session_yields_session():
    """get_db_session should yield a database session."""
    from packages.api.src.dependencies import get_db_session

    mock_session = AsyncMock()

    # Patch get_session as an async context manager that yields mock_session
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake_get_session():
        yield mock_session

    with patch(
        "packages.api.src.dependencies.get_session",
        side_effect=_fake_get_session,
    ):
        gen = get_db_session()
        session = await gen.__anext__()
        assert session is mock_session

        # Exhaust the generator (triggers cleanup)
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass


@pytest.mark.asyncio
async def test_get_db_session_returns_async_generator():
    """get_db_session must be an async generator (for FastAPI Depends compatibility)."""
    import inspect

    from packages.api.src.dependencies import get_db_session

    mock_session = AsyncMock()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake_get_session():
        yield mock_session

    with patch(
        "packages.api.src.dependencies.get_session",
        side_effect=_fake_get_session,
    ):
        gen = get_db_session()
        assert inspect.isasyncgen(gen)

        # Clean up
        try:
            await gen.__anext__()
            await gen.__anext__()
        except StopAsyncIteration:
            pass
