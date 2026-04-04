"""Tests for challenge-aligned research brief generation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from packages.research.src.aggregator.sweep import PaperResult, RepoResult
from packages.research.src.task_research_brief import (
    ChallengeResearchContext,
    generate_architecture_phase_seed_docs,
    run_architecture_followup_research,
    run_challenge_research_brief,
)


def _sample_repo() -> RepoResult:
    return RepoResult(
        name="demo",
        full_name="org/demo",
        url="https://github.com/org/demo",
        description="Demo queue service",
        stars=42,
        last_pushed="2025-06-01",
        language="Python",
        topics=["fastapi", "redis"],
        open_issues=3,
        license_name="MIT",
        readme_url=None,
    )


def _sample_paper() -> PaperResult:
    return PaperResult(
        title="Distributed task scheduling",
        authors=["A. Researcher"],
        abstract="We study task queues and workers in cloud settings.",
        url="https://arxiv.org/abs/2401.00001",
        published="2025-01-15",
        categories=["cs.DC"],
    )


@pytest.mark.asyncio
async def test_run_challenge_research_brief_writes_expected_keys() -> None:
    ctx = ChallengeResearchContext(
        title="Build a Task Queue API",
        challenge_id="task-queue-engine",
        requirements=["POST to enqueue", "GET status"],
        category="api_service",
    )
    with (
        patch(
            "packages.research.src.task_research_brief.GitHubSearcher.search_repos",
            new=AsyncMock(return_value=[_sample_repo()]),
        ),
        patch(
            "packages.research.src.task_research_brief.ArxivSearcher.search",
            new=AsyncMock(return_value=[_sample_paper()]),
        ),
        patch("packages.research.src.task_research_brief.asyncio.sleep", new=AsyncMock()),
    ):
        out = await run_challenge_research_brief(
            ctx,
            github_token=None,
            arxiv_max_per_query=3,
            github_per_query=5,
            llm_client=None,
            peer_review_with_llm=False,
        )

    assert set(out) == {
        "RESEARCH.md",
        "USE_CASES.md",
        "PEER_REVIEW.md",
        "RESEARCH_QUERIES.md",
    }
    assert "org/demo" in out["RESEARCH.md"]
    assert "Distributed task scheduling" in out["RESEARCH.md"]
    assert "UC-1" in out["USE_CASES.md"]
    assert "POST to enqueue" in out["USE_CASES.md"]
    assert "Peer review" in out["PEER_REVIEW.md"]
    assert "GitHub" in out["RESEARCH_QUERIES.md"]


@pytest.mark.asyncio
async def test_run_architecture_followup_research_keys() -> None:
    ctx = ChallengeResearchContext(
        title="Build a Task Queue API",
        challenge_id="task-queue-engine",
        requirements=["POST to enqueue"],
        category="api_service",
    )
    with (
        patch(
            "packages.research.src.task_research_brief.GitHubSearcher.search_repos",
            new=AsyncMock(return_value=[_sample_repo()]),
        ),
        patch(
            "packages.research.src.task_research_brief.ArxivSearcher.search",
            new=AsyncMock(return_value=[_sample_paper()]),
        ),
        patch("packages.research.src.task_research_brief.asyncio.sleep", new=AsyncMock()),
    ):
        out = await run_architecture_followup_research(
            ctx,
            github_token=None,
            arxiv_max_per_query=2,
            github_per_query=4,
        )
    assert set(out) == {"RESEARCH_ARCHITECTURE.md", "RESEARCH_QUERIES_ARCHITECTURE.md"}
    assert "Architecture follow-up research" in out["RESEARCH_ARCHITECTURE.md"]
    assert "Architecture-phase queries" in out["RESEARCH_QUERIES_ARCHITECTURE.md"]


@pytest.mark.asyncio
async def test_generate_architecture_phase_seed_docs_template() -> None:
    ctx = ChallengeResearchContext(
        title="Build a Task Queue API",
        challenge_id="task-queue-engine",
        requirements=["POST to enqueue jobs"],
        category="api_service",
    )
    bundle = {
        "RESEARCH.md": "x",
        "PEER_REVIEW.md": "Risks include scaling.",
    }
    out = await generate_architecture_phase_seed_docs(
        ctx,
        bundle,
        llm_client=None,
        seed_with_llm=False,
        extra_architecture_research="Microservices patterns.",
    )
    assert set(out) == {"ARCHITECTURE_SEED.md", "REQUIREMENTS_TRACE.md"}
    assert "Architecture seed" in out["ARCHITECTURE_SEED.md"]
    assert "RESEARCH_ARCHITECTURE.md" in out["ARCHITECTURE_SEED.md"]
    assert "Requirements trace" in out["REQUIREMENTS_TRACE.md"]
    assert "POST to enqueue" in out["REQUIREMENTS_TRACE.md"]
