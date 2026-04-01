"""
AgentForge Arena — Tests for Route Mounting and App Factory

Verifies that all route modules are properly mounted and inline stubs
have been replaced. Does NOT test business logic — only that endpoints
exist and respond (not 404/405).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture()
def mock_services() -> dict:
    """Create mock services matching what lifespan stores on app.state."""
    orchestrator = MagicMock()
    orchestrator._active_tournaments = {}
    orchestrator.create_tournament = AsyncMock()
    orchestrator.start_tournament = AsyncMock()
    orchestrator.cancel_tournament = AsyncMock()

    agent_manager = MagicMock()
    agent_manager.get_team_agents = AsyncMock(return_value=[])

    db_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db_session.execute.return_value = mock_result

    return {
        "orchestrator": orchestrator,
        "agent_manager": agent_manager,
        "db_session": db_session,
    }


@pytest.fixture()
def test_app(mock_services: dict) -> FastAPI:
    """Build the app with route modules mounted and dependencies overridden."""
    from packages.api.src.main import _register_routes
    from packages.api.src.dependencies import (
        get_agent_manager,
        get_db_session,
        get_orchestrator,
    )

    app = FastAPI()

    # Override dependencies
    app.dependency_overrides[get_orchestrator] = lambda: mock_services["orchestrator"]
    app.dependency_overrides[get_agent_manager] = lambda: mock_services["agent_manager"]

    async def override_db():
        yield mock_services["db_session"]

    app.dependency_overrides[get_db_session] = override_db

    _register_routes(app)
    return app


@pytest.fixture()
def client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app, raise_server_exceptions=False)


# ============================================================
# Route existence tests — verify no 404s
# ============================================================


class TestRouteMounting:
    """Verify all expected endpoints are mounted and reachable."""

    def test_health_endpoint_exists(self, client: TestClient) -> None:
        """GET /health should return 200."""
        # Health check does a Redis ping, which will fail without real Redis.
        # But the route should exist (not 404).
        response = client.get("/health")
        # May be 200 or 500 (if Redis unavailable), but NOT 404
        assert response.status_code != 404

    def test_tournament_list_exists(self, client: TestClient) -> None:
        """GET /api/v1/tournaments returns 200."""
        response = client.get("/api/v1/tournaments")
        assert response.status_code == 200

    def test_tournament_create_exists(self, client: TestClient) -> None:
        """POST /api/v1/tournaments is reachable (may be 422 without body)."""
        response = client.post("/api/v1/tournaments", json={})
        # 422 (validation) or 400 is fine — proves route exists
        assert response.status_code in (201, 400, 422)

    def test_tournament_get_exists(self, client: TestClient) -> None:
        """GET /api/v1/tournaments/{id} returns 404 for unknown ID (not 405)."""
        response = client.get(f"/api/v1/tournaments/{uuid4()}")
        assert response.status_code == 404

    def test_tournament_start_exists(self, client: TestClient) -> None:
        """POST /api/v1/tournaments/{id}/start returns 404 for unknown ID."""
        response = client.post(f"/api/v1/tournaments/{uuid4()}/start")
        assert response.status_code == 404

    def test_tournament_cancel_exists(self, client: TestClient) -> None:
        """POST /api/v1/tournaments/{id}/cancel returns 404 for unknown ID."""
        response = client.post(f"/api/v1/tournaments/{uuid4()}/cancel")
        assert response.status_code == 404

    def test_leaderboard_exists(self, client: TestClient) -> None:
        """GET /api/v1/leaderboard returns 200."""
        response = client.get("/api/v1/leaderboard")
        assert response.status_code == 200

    def test_challenges_list_exists(self, client: TestClient) -> None:
        """GET /api/v1/challenges returns 200."""
        response = client.get("/api/v1/challenges")
        assert response.status_code == 200

    def test_challenges_get_exists(self, client: TestClient) -> None:
        """GET /api/v1/challenges/{id} returns 404 for unknown challenge."""
        response = client.get("/api/v1/challenges/nonexistent")
        assert response.status_code == 404

    def test_agents_list_exists(self, client: TestClient) -> None:
        """GET /api/v1/tournaments/{id}/agents returns 404 for unknown tournament."""
        response = client.get(f"/api/v1/tournaments/{uuid4()}/agents")
        assert response.status_code == 404


class TestInlineStubsRemoved:
    """Verify that inline stubs from main.py have been replaced with real routes."""

    def test_tournament_list_returns_structured_response(
        self, client: TestClient
    ) -> None:
        """List tournaments should return proper paginated structure, not a stub dict."""
        response = client.get("/api/v1/tournaments")
        body = response.json()

        # Real route returns TournamentListResponse with these keys
        assert "tournaments" in body
        assert "total" in body
        assert "offset" in body
        assert "limit" in body

    def test_leaderboard_returns_structured_response(
        self, client: TestClient
    ) -> None:
        """Leaderboard should return LeaderboardResponse, not stub."""
        response = client.get("/api/v1/leaderboard")
        body = response.json()

        assert "entries" in body
        assert "total" in body
        assert "updated_at" in body

    def test_challenges_returns_structured_response(
        self, client: TestClient
    ) -> None:
        """Challenges should return ChallengeListResponse, not stub."""
        response = client.get("/api/v1/challenges")
        body = response.json()

        assert "challenges" in body
        assert "total" in body
