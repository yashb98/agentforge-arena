"""Tests for ContextCompressor (Haiku 4.5 summarization)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from packages.memory.src.compression.compressor import CompressedContext, ContextCompressor
from packages.memory.src.working.models import WorkingState
from packages.shared.src.types.models import AgentRole, TournamentPhase


@pytest.fixture()
def mock_llm():
    """Mock LLM client returning a summary."""
    client = MagicMock()
    client.completion = AsyncMock(
        return_value=MagicMock(
            content="Agent built auth module with bcrypt. Pending: rate limiting.",
            usage=MagicMock(total_tokens=200, cost_usd=0.001),
        )
    )
    return client


@pytest.fixture()
def compressor(mock_llm) -> ContextCompressor:
    return ContextCompressor(llm_client=mock_llm)


@pytest.fixture()
def big_state() -> WorkingState:
    return WorkingState(
        agent_id=uuid4(),
        team_id=uuid4(),
        role=AgentRole.BUILDER,
        current_phase=TournamentPhase.BUILD,
        current_task="Build auth module",
        recent_decisions=[f"Decision {i}: detailed reasoning about choice {i}" for i in range(10)],
        recent_files_touched=[f"src/file_{i}.py" for i in range(20)],
        active_errors=["Error: connection refused"],
        context_summary="Previous context about the project setup.",
    )


class TestContextCompressor:
    """Tests for Haiku-based context compression."""

    @pytest.mark.asyncio
    async def test_compress_returns_compressed_context(
        self, compressor, big_state
    ) -> None:
        """compress() should return a CompressedContext."""
        result = await compressor.compress(big_state)
        assert isinstance(result, CompressedContext)
        assert len(result.summary) > 0

    @pytest.mark.asyncio
    async def test_compress_preserves_top_3_decisions(
        self, compressor, big_state
    ) -> None:
        """compress() should preserve the 3 most recent decisions."""
        result = await compressor.compress(big_state)
        assert len(result.preserved_decisions) == 3

    @pytest.mark.asyncio
    async def test_compress_reports_dropped_count(
        self, compressor, big_state
    ) -> None:
        """compress() should report how many items were dropped."""
        result = await compressor.compress(big_state)
        assert result.dropped_count > 0

    @pytest.mark.asyncio
    async def test_compress_calls_llm_with_haiku(self, compressor, mock_llm, big_state) -> None:
        """compress() should call LLM with claude-haiku-4-5 model."""
        await compressor.compress(big_state)
        call_kwargs = mock_llm.completion.call_args
        assert call_kwargs.kwargs["model"] == "claude-haiku-4-5"

    @pytest.mark.asyncio
    async def test_apply_compressed_updates_state(self, compressor, big_state) -> None:
        """apply() should update the working state with compressed data."""
        compressed = CompressedContext(
            summary="Compressed summary of work.",
            preserved_decisions=["Decision 9", "Decision 8", "Decision 7"],
            dropped_count=7,
        )
        updated = compressor.apply(big_state, compressed)
        assert updated.context_summary == "Compressed summary of work."
        assert len(updated.recent_decisions) == 3
        assert len(updated.recent_files_touched) == 10  # Trimmed to last 10
        assert len(updated.active_errors) == 1  # Errors never compressed
