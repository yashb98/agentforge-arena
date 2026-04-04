"""Research sweep circuit breakers and auxiliary sources."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from packages.research.src.aggregator.sweep import ResearchSweep


@pytest.mark.asyncio
async def test_full_scope_runs_web_and_semantic_scholar_tasks() -> None:
    sweep = ResearchSweep(scope="full")
    sweep.github.search_repos = AsyncMock(return_value=[])
    sweep.arxiv.search = AsyncMock(return_value=[])
    sweep.packages.search_pypi = AsyncMock(return_value=None)
    sweep.duckduckgo.instant_summary = AsyncMock(return_value=["ddg snippet"])
    sweep.semantic_scholar.search_titles = AsyncMock(return_value=["Paper — https://x"])

    report = await sweep.run("agent tournament")

    assert report.web_instant_snippets == ["ddg snippet"]
    assert report.scholar_hits == ["Paper — https://x"]


@pytest.mark.asyncio
async def test_papers_scope_skips_web_tasks() -> None:
    sweep = ResearchSweep(scope="papers")
    sweep.arxiv.search = AsyncMock(return_value=[])
    sweep.duckduckgo.instant_summary = AsyncMock(return_value=["should-not-run"])

    await sweep.run("q")

    sweep.duckduckgo.instant_summary.assert_not_called()
