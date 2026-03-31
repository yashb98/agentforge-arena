"""
AgentForge Arena — Root Test Configuration

Shared pytest fixtures used across all package tests.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio

from packages.shared.src.types.models import (
    AgentConfig,
    AgentRole,
    Challenge,
    ChallengeCategory,
    ChallengeDifficulty,
    ModelProvider,
    TeamConfig,
    Tournament,
    TournamentConfig,
    TournamentFormat,
)


# ============================================================
# Event Loop
# ============================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============================================================
# Model Factories
# ============================================================

@pytest.fixture
def sample_agent_config() -> AgentConfig:
    """Create a sample agent configuration."""
    return AgentConfig(
        role=AgentRole.BUILDER,
        model=ModelProvider.CLAUDE_SONNET_4_6,
        temperature=0.3,
        max_tokens=8192,
        timeout_seconds=300,
        tools=["read(**)", "write(src/**)", "bash(pytest *)"],
    )


@pytest.fixture
def sample_team_config() -> TeamConfig:
    """Create a balanced team configuration."""
    return TeamConfig(
        name="Team Alpha",
        preset="balanced",
        agents=[
            AgentConfig(role=AgentRole.ARCHITECT, model=ModelProvider.CLAUDE_OPUS_4_6),
            AgentConfig(role=AgentRole.BUILDER, model=ModelProvider.CLAUDE_SONNET_4_6),
            AgentConfig(role=AgentRole.FRONTEND, model=ModelProvider.CLAUDE_SONNET_4_6),
            AgentConfig(role=AgentRole.TESTER, model=ModelProvider.CLAUDE_HAIKU_4_5),
            AgentConfig(role=AgentRole.CRITIC, model=ModelProvider.CLAUDE_OPUS_4_6),
        ],
    )


@pytest.fixture
def sample_tournament_config(sample_team_config: TeamConfig) -> TournamentConfig:
    """Create a sample duel tournament configuration."""
    team_b = sample_team_config.model_copy(update={"name": "Team Beta"})
    return TournamentConfig(
        format=TournamentFormat.DUEL,
        challenge_id="url-shortener-saas",
        teams=[sample_team_config, team_b],
        budget_limit_usd=200.0,
    )


@pytest.fixture
def sample_challenge() -> Challenge:
    """Create a sample challenge."""
    return Challenge(
        id="url-shortener-saas",
        title="URL Shortener SaaS",
        description="Build a production-ready URL shortener with analytics.",
        category=ChallengeCategory.SAAS_APP,
        difficulty=ChallengeDifficulty.MEDIUM,
        time_limit_minutes=90,
        requirements=[
            "Create short URL from long URL",
            "Redirect short URL to original",
            "Track click analytics",
            "List all URLs for a user",
            "Delete a short URL",
        ],
        hidden_test_hints=[
            "Judge tests 1000+ URL creations",
            "Judge tests redirect latency (<50ms p99)",
            "Judge tests concurrent redirects (100 simultaneous)",
        ],
        tags=["saas", "api", "database", "caching"],
    )


# ============================================================
# Redis Fixtures
# ============================================================

@pytest_asyncio.fixture
async def fake_redis():
    """Create a fakeredis instance for testing."""
    try:
        import fakeredis.aioredis
        redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
        yield redis
        await redis.close()
    except ImportError:
        pytest.skip("fakeredis not installed")


# ============================================================
# Event Bus Fixtures
# ============================================================

@pytest_asyncio.fixture
async def event_bus(fake_redis):
    """Create an EventBus with fake Redis for testing."""
    from packages.shared.src.events.bus import EventBus
    bus = EventBus(fake_redis)
    yield bus
    await bus.stop()


# ============================================================
# Utility Fixtures
# ============================================================

@pytest.fixture
def random_uuid():
    """Generate a random UUID."""
    return uuid4()


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temporary workspace directory structure."""
    workspace = tmp_path / "arena" / "team-test" / "project"
    workspace.mkdir(parents=True)
    (workspace / "src").mkdir()
    (workspace / "tests").mkdir()
    (workspace / ".claude" / "rules").mkdir(parents=True)
    return workspace
