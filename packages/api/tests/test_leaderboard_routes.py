"""
AgentForge Arena — Tests for Leaderboard Routes

Covers:
  GET /api/v1/leaderboard — empty DB, populated DB, category filtering
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.api.src.routes.leaderboard import router
from packages.shared.src.types.responses import LeaderboardResponse


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture()
def mock_db_session() -> AsyncMock:
    """Mock async DB session."""
    session = AsyncMock()
    return session


def _make_elo_row(
    config_name: str = "balanced",
    rating: float = 1500.0,
    ci_lower: float = 1400.0,
    ci_upper: float = 1600.0,
    matches_played: int = 10,
    wins: int = 6,
    losses: int = 4,
    draws: int = 0,
    category: str = "overall",
) -> MagicMock:
    """Create a mock EloRatingDB row."""
    row = MagicMock()
    row.config_name = config_name
    row.rating = rating
    row.ci_lower = ci_lower
    row.ci_upper = ci_upper
    row.matches_played = matches_played
    row.wins = wins
    row.losses = losses
    row.draws = draws
    row.category = category
    row.updated_at = datetime.utcnow()
    return row


@pytest.fixture()
def test_app(mock_db_session: AsyncMock) -> FastAPI:
    """Minimal FastAPI app with leaderboard router and mocked DB."""
    app = FastAPI()

    from packages.api.src.dependencies import get_db_session

    async def override_db():
        yield mock_db_session

    app.dependency_overrides[get_db_session] = override_db
    app.include_router(router)
    return app


@pytest.fixture()
def client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app, raise_server_exceptions=False)


# ============================================================
# GET /api/v1/leaderboard
# ============================================================


class TestGetLeaderboard:
    """Tests for GET /leaderboard."""

    def test_returns_200_with_empty_leaderboard(
        self,
        client: TestClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """No ELO ratings in DB → 200 with empty entries."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = client.get("/api/v1/leaderboard")

        assert response.status_code == 200
        body = response.json()
        assert body["entries"] == []
        assert body["total"] == 0

    def test_returns_entries_sorted_by_rating(
        self,
        client: TestClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """Rows from DB are returned as leaderboard entries."""
        rows = [
            _make_elo_row("aggressive", rating=1650.0, wins=8, losses=2),
            _make_elo_row("balanced", rating=1500.0, wins=5, losses=5),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        mock_db_session.execute.return_value = mock_result

        response = client.get("/api/v1/leaderboard")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert body["entries"][0]["team_config_name"] == "aggressive"
        assert body["entries"][0]["elo_rating"] == 1650.0
        assert body["entries"][1]["team_config_name"] == "balanced"

    def test_entries_have_correct_win_rate(
        self,
        client: TestClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """Win rate is computed from wins/matches_played."""
        rows = [_make_elo_row("test", wins=7, losses=3, matches_played=10)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        mock_db_session.execute.return_value = mock_result

        response = client.get("/api/v1/leaderboard")

        body = response.json()
        assert body["entries"][0]["win_rate"] == pytest.approx(0.7)

    def test_has_updated_at_timestamp(
        self,
        client: TestClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """Response includes updated_at timestamp."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = client.get("/api/v1/leaderboard")

        body = response.json()
        assert "updated_at" in body

    def test_accepts_category_query_param(
        self,
        client: TestClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """Category param is forwarded to DB query."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = client.get("/api/v1/leaderboard?category=per_model")

        assert response.status_code == 200
        # Verify execute was called (the query filters by category)
        mock_db_session.execute.assert_awaited_once()
