"""Test fixtures — Team Alpha."""
from __future__ import annotations

import asyncio
import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src import database


@pytest.fixture(autouse=True)
async def setup_db():
    """Use in-memory DB for each test."""
    await database.init_db(":memory:")
    yield
    await database.close_db()


@pytest.fixture
async def client():
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
