"""
AgentForge Arena — Tests for Challenge Loading & Selection

Tests _load_challenge() and _select_random_challenge() from the orchestrator,
plus scoring_config.json parsing.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from packages.core.src.tournament.orchestrator import TournamentOrchestrator


# ============================================================
# Fixtures
# ============================================================

REPO_ROOT = Path(__file__).resolve().parents[3]
CHALLENGE_LIBRARY = REPO_ROOT / "challenges" / "library"


@pytest.fixture()
def orchestrator() -> TournamentOrchestrator:
    """Create orchestrator with mocked dependencies."""
    return TournamentOrchestrator(
        event_bus=MagicMock(),
        sandbox_manager=MagicMock(),
        agent_manager=MagicMock(),
        judge_service=MagicMock(),
    )


# ============================================================
# Challenge Library Structure Tests
# ============================================================


class TestChallengeLibraryStructure:
    """Verify the challenge library is properly structured."""

    def test_library_directory_exists(self) -> None:
        assert CHALLENGE_LIBRARY.is_dir(), f"Challenge library not found at {CHALLENGE_LIBRARY}"

    def test_at_least_three_challenges_exist(self) -> None:
        challenges = [
            d.name for d in CHALLENGE_LIBRARY.iterdir()
            if d.is_dir() and (d / "CHALLENGE.md").is_file()
        ]
        assert len(challenges) >= 3, f"Expected >=3 challenges, found {challenges}"

    @pytest.mark.parametrize("slug", [
        "url-shortener-saas",
        "realtime-chat-app",
        "task-queue-engine",
    ])
    def test_challenge_has_required_files(self, slug: str) -> None:
        challenge_dir = CHALLENGE_LIBRARY / slug
        assert challenge_dir.is_dir(), f"Challenge directory missing: {slug}"
        assert (challenge_dir / "CHALLENGE.md").is_file(), f"CHALLENGE.md missing for {slug}"
        assert (challenge_dir / "challenge.spec.json").is_file(), (
            f"challenge.spec.json missing for {slug}"
        )
        assert (challenge_dir / "hidden_tests").is_dir(), f"hidden_tests/ missing for {slug}"
        assert (challenge_dir / "scoring_config.json").is_file(), f"scoring_config.json missing for {slug}"

    @pytest.mark.parametrize("slug", [
        "url-shortener-saas",
        "realtime-chat-app",
        "task-queue-engine",
    ])
    def test_hidden_tests_have_conftest(self, slug: str) -> None:
        conftest = CHALLENGE_LIBRARY / slug / "hidden_tests" / "conftest.py"
        assert conftest.is_file(), f"conftest.py missing in {slug}/hidden_tests/"

    @pytest.mark.parametrize("slug", [
        "url-shortener-saas",
        "realtime-chat-app",
        "task-queue-engine",
    ])
    def test_hidden_tests_have_test_files(self, slug: str) -> None:
        test_dir = CHALLENGE_LIBRARY / slug / "hidden_tests"
        test_files = list(test_dir.glob("test_*.py"))
        assert len(test_files) >= 2, f"Expected >=2 test files in {slug}, found {len(test_files)}"


# ============================================================
# Challenge Loading Tests
# ============================================================


class TestLoadChallenge:
    """Test _load_challenge() reads the correct CHALLENGE.md."""

    @pytest.mark.asyncio
    async def test_load_existing_challenge(self, orchestrator: TournamentOrchestrator) -> None:
        content = await orchestrator._load_challenge("url-shortener-saas")
        assert "# Challenge:" in content
        assert "URL Shortener" in content
        assert "Requirements" in content

    @pytest.mark.asyncio
    async def test_load_all_challenges(self, orchestrator: TournamentOrchestrator) -> None:
        for slug in ("url-shortener-saas", "realtime-chat-app", "task-queue-engine"):
            content = await orchestrator._load_challenge(slug)
            assert "# Challenge:" in content
            assert "Requirements" in content

    @pytest.mark.asyncio
    async def test_load_nonexistent_challenge_returns_fallback(
        self, orchestrator: TournamentOrchestrator
    ) -> None:
        content = await orchestrator._load_challenge("nonexistent-challenge-xyz")
        assert "not found" in content.lower() or "nonexistent" in content


# ============================================================
# Challenge Selection Tests
# ============================================================


class TestSelectRandomChallenge:
    """Test _select_random_challenge() picks from the library."""

    @pytest.mark.asyncio
    async def test_selects_from_library(self, orchestrator: TournamentOrchestrator) -> None:
        selected = await orchestrator._select_random_challenge()
        valid = {"url-shortener-saas", "realtime-chat-app", "task-queue-engine"}
        assert selected in valid, f"Unexpected challenge: {selected}"

    @pytest.mark.asyncio
    async def test_returns_string(self, orchestrator: TournamentOrchestrator) -> None:
        selected = await orchestrator._select_random_challenge()
        assert isinstance(selected, str)
        assert len(selected) > 0


# ============================================================
# Scoring Config Tests
# ============================================================


class TestScoringConfig:
    """Test scoring_config.json parsing."""

    @pytest.mark.parametrize("slug", [
        "url-shortener-saas",
        "realtime-chat-app",
        "task-queue-engine",
    ])
    def test_scoring_config_is_valid_json(self, slug: str) -> None:
        config_file = CHALLENGE_LIBRARY / slug / "scoring_config.json"
        data = json.loads(config_file.read_text())
        assert "scoring_weights" in data
        assert isinstance(data["scoring_weights"], dict)

    @pytest.mark.parametrize("slug", [
        "url-shortener-saas",
        "realtime-chat-app",
        "task-queue-engine",
    ])
    def test_scoring_weights_sum_to_one(self, slug: str) -> None:
        config_file = CHALLENGE_LIBRARY / slug / "scoring_config.json"
        data = json.loads(config_file.read_text())
        weights = data["scoring_weights"]
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected 1.0"

    @pytest.mark.parametrize("slug", [
        "url-shortener-saas",
        "realtime-chat-app",
        "task-queue-engine",
    ])
    def test_scoring_config_has_expected_port(self, slug: str) -> None:
        config_file = CHALLENGE_LIBRARY / slug / "scoring_config.json"
        data = json.loads(config_file.read_text())
        assert data.get("expected_port") == 8000

    @pytest.mark.parametrize("slug", [
        "url-shortener-saas",
        "realtime-chat-app",
        "task-queue-engine",
    ])
    def test_scoring_config_has_timeout(self, slug: str) -> None:
        config_file = CHALLENGE_LIBRARY / slug / "scoring_config.json"
        data = json.loads(config_file.read_text())
        assert "hidden_test_timeout_seconds" in data
        assert data["hidden_test_timeout_seconds"] > 0
