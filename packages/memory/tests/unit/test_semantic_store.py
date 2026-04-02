"""Tests for L3 SemanticStore (Qdrant)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from packages.memory.src.semantic.models import CodeChunk, SearchResult
from packages.memory.src.semantic.store import SemanticStore


@pytest.fixture()
def store(mock_qdrant, team_id) -> SemanticStore:
    mock_embedder = MagicMock()
    mock_embedder.embed_query = AsyncMock(return_value=[0.1] * 384)
    return SemanticStore(
        qdrant=mock_qdrant,
        embedder=mock_embedder,
        team_id=team_id,
    )


@pytest.fixture()
def sample_chunks() -> list[CodeChunk]:
    return [
        CodeChunk(
            chunk_id="src/auth.py::login",
            file_path="src/auth.py",
            language="python",
            module_name="auth",
            symbol_name="login",
            symbol_type="function",
            content="def login(user, pw): ...",
            line_start=1,
            line_end=10,
        ),
        CodeChunk(
            chunk_id="src/auth.py::logout",
            file_path="src/auth.py",
            language="python",
            module_name="auth",
            symbol_name="logout",
            symbol_type="function",
            content="def logout(token): ...",
            line_start=12,
            line_end=20,
        ),
    ]


class TestSemanticStore:
    """Tests for Qdrant-backed semantic search."""

    def test_collection_name(self, store, team_id) -> None:
        """Collection name should include team_id."""
        assert str(team_id) in store.collection_name

    @pytest.mark.asyncio
    async def test_ensure_collection_creates_if_missing(
        self, store, mock_qdrant
    ) -> None:
        """ensure_collection() should create collection if it doesn't exist."""
        mock_qdrant.collection_exists = AsyncMock(return_value=False)
        await store.ensure_collection()
        mock_qdrant.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_collection_skips_if_exists(
        self, store, mock_qdrant
    ) -> None:
        """ensure_collection() should skip if collection exists."""
        mock_qdrant.collection_exists = AsyncMock(return_value=True)
        await store.ensure_collection()
        mock_qdrant.create_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_chunks(
        self, store, mock_qdrant, sample_chunks
    ) -> None:
        """upsert() should call Qdrant upsert with correct data."""
        mock_embedder = store._embedder
        mock_embedder.embed_bulk = AsyncMock(return_value=[[0.1] * 384, [0.2] * 384])
        await store.upsert(sample_chunks)
        mock_qdrant.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_returns_results(self, store, mock_qdrant) -> None:
        """search() should return SearchResult list."""
        mock_point = MagicMock()
        mock_point.id = "src/auth.py::login"
        mock_point.score = 0.92
        mock_point.payload = {
            "file_path": "src/auth.py",
            "language": "python",
            "module_name": "auth",
            "symbol_name": "login",
            "symbol_type": "function",
            "content": "def login(): ...",
            "line_start": 1,
            "line_end": 10,
        }
        mock_qdrant.search = AsyncMock(return_value=[mock_point])

        results = await store.search("login function", limit=5)
        assert len(results) == 1
        assert results[0].source == "semantic"
        assert results[0].score == 0.92

    @pytest.mark.asyncio
    async def test_delete_by_file(self, store, mock_qdrant) -> None:
        """delete_by_file() should delete points matching file_path."""
        await store.delete_by_file("src/auth.py")
        mock_qdrant.delete.assert_called_once()
