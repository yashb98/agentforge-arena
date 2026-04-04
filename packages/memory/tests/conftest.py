"""Shared fixtures for memory package tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


@pytest.fixture
def team_id():
    return uuid4()


@pytest.fixture
def tournament_id():
    return uuid4()


@pytest.fixture
def agent_id():
    return uuid4()


@pytest.fixture
def mock_redis():
    """Create a mock async Redis client."""
    r = MagicMock()
    r.hset = AsyncMock()
    r.hgetall = AsyncMock(return_value={})
    r.delete = AsyncMock()
    r.expire = AsyncMock()
    r.set = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.exists = AsyncMock(return_value=0)
    return r


@pytest.fixture
def mock_qdrant():
    """Create a mock QdrantClient."""
    client = MagicMock()
    client.upsert = AsyncMock()
    client.search = AsyncMock(return_value=[])
    client.delete = AsyncMock()
    client.create_collection = AsyncMock()
    client.collection_exists = AsyncMock(return_value=False)
    return client
