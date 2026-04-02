"""Tests for HybridEmbedder (FastEmbed + LiteLLM)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from packages.memory.src.semantic.embedder import HybridEmbedder


@pytest.fixture
def mock_fastembed():
    """Mock FastEmbed TextEmbedding."""
    fe = MagicMock()
    fe.embed = MagicMock(return_value=iter([[0.1] * 384, [0.2] * 384]))
    return fe


@pytest.fixture
def embedder(mock_fastembed) -> HybridEmbedder:
    return HybridEmbedder(fastembed_model=mock_fastembed, llm_client=None)


class TestHybridEmbedder:
    """Tests for the hybrid embedding strategy."""

    @pytest.mark.asyncio
    async def test_embed_bulk_uses_fastembed(self, embedder, mock_fastembed) -> None:
        """embed_bulk() should use FastEmbed for batch indexing."""
        results = await embedder.embed_bulk(["code 1", "code 2"])
        assert len(results) == 2
        assert len(results[0]) == 384
        mock_fastembed.embed.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_query_without_llm_falls_back_to_fastembed(
        self,
        embedder,
        mock_fastembed,
    ) -> None:
        """embed_query() without LLM client should fall back to FastEmbed."""
        mock_fastembed.embed = MagicMock(return_value=iter([[0.5] * 384]))
        result = await embedder.embed_query("search query")
        assert len(result) == 384

    @pytest.mark.asyncio
    async def test_embed_query_with_llm_uses_llm(self, mock_fastembed) -> None:
        """embed_query() with LLM client should use LiteLLM for higher quality."""
        mock_llm = MagicMock()
        mock_llm.completion = AsyncMock(
            return_value=MagicMock(raw={"data": [{"embedding": [0.9] * 384}]}),
        )
        embedder = HybridEmbedder(fastembed_model=mock_fastembed, llm_client=mock_llm)
        result = await embedder.embed_query("search query")
        assert len(result) == 384

    @pytest.mark.asyncio
    async def test_embed_bulk_empty_list(self, embedder) -> None:
        """embed_bulk() with empty list should return empty list."""
        results = await embedder.embed_bulk([])
        assert results == []
