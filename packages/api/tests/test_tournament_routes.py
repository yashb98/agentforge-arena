"""
AgentForge Arena — Tests for Tournament Route Handlers

Covers every endpoint in packages/api/src/routes/tournaments.py:
    POST   /tournaments              create_tournament
    GET    /tournaments              list_tournaments
    GET    /tournaments/{id}         get_tournament
    POST   /tournaments/{id}/start   start_tournament
    POST   /tournaments/{id}/cancel  cancel_tournament

All Anthropic / external I/O is mocked.  The FastAPI test client is
used for HTTP-level assertions.  No real DB or Redis is required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.api.src.routes.tournaments import _tournament_to_response, router
from packages.shared.src.types.models import (
    AgentConfig,
    AgentRole,
    ModelProvider,
    Team,
    TeamConfig,
    Tournament,
    TournamentConfig,
    TournamentFormat,
    TournamentPhase,
)
from packages.shared.src.types.responses import TeamSummary, TournamentResponse


# ============================================================
# Helpers / factories
# ============================================================

def _make_agent_config() -> AgentConfig:
    return AgentConfig(
        role=AgentRole.ARCHITECT,
        model=ModelProvider.CLAUDE_SONNET_4_6,
        temperature=0.3,
        max_tokens=8192,
        timeout_seconds=300,
        tools=[],
    )


def _make_team_config(name: str = "alpha") -> TeamConfig:
    return TeamConfig(
        name=name,
        preset="balanced",
        agents=[_make_agent_config(), _make_agent_config(), _make_agent_config()],
        sandbox_memory="4g",
        sandbox_cpus=2,
    )


def _make_tournament_config(
    fmt: TournamentFormat = TournamentFormat.DUEL,
) -> TournamentConfig:
    return TournamentConfig(
        format=fmt,
        challenge_id="url-shortener-saas",
        teams=[_make_team_config("alpha"), _make_team_config("beta")],
        budget_limit_usd=100.0,
    )


def _make_tournament(
    *,
    phase: TournamentPhase = TournamentPhase.PREP,
    team_ids: list[UUID] | None = None,
) -> Tournament:
    tid = uuid4()
    cfg = _make_tournament_config()
    return Tournament(
        id=tid,
        format=TournamentFormat.DUEL,
        current_phase=phase,
        challenge_id="url-shortener-saas",
        config=cfg,
        team_ids=team_ids or [uuid4(), uuid4()],
        total_cost_usd=0.0,
    )


def _make_team(tournament_id: UUID, name: str = "alpha") -> Team:
    return Team(
        id=uuid4(),
        tournament_id=tournament_id,
        name=name,
        config=_make_team_config(name),
        agent_ids=[uuid4(), uuid4(), uuid4()],
        total_cost_usd=1.23,
    )


# ============================================================
# App + client fixtures
# ============================================================

@pytest.fixture()
def mock_orchestrator() -> MagicMock:
    """A mock TournamentOrchestrator with an empty active_tournaments registry."""
    orch = MagicMock()
    orch._active_tournaments = {}
    orch.create_tournament = AsyncMock()
    orch.start_tournament = AsyncMock()
    orch.cancel_tournament = AsyncMock()
    return orch


@pytest.fixture()
def test_app(mock_orchestrator: MagicMock) -> FastAPI:
    """Minimal FastAPI app with the tournament router and mocked dependencies."""
    app = FastAPI()

    # Override the dependency so no real app state is needed
    from packages.api.src.dependencies import get_orchestrator

    app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture()
def client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app, raise_server_exceptions=False)


# ============================================================
# _tournament_to_response unit tests
# ============================================================

class TestTournamentToResponse:
    """Unit tests for the _tournament_to_response helper."""

    def test_maps_basic_fields(self) -> None:
        """All scalar fields from Tournament are copied correctly."""
        t = _make_tournament()
        resp = _tournament_to_response(t)

        assert resp.id == t.id
        assert resp.format == t.format
        assert resp.current_phase == t.current_phase
        assert resp.challenge_id == t.challenge_id
        assert resp.total_cost_usd == t.total_cost_usd

    def test_uses_provided_teams_for_summaries(self) -> None:
        """When teams are supplied, summaries include agent counts and costs."""
        t = _make_tournament()
        team_a = _make_team(t.id, "alpha")
        team_b = _make_team(t.id, "beta")

        resp = _tournament_to_response(t, teams=[team_a, team_b])

        assert len(resp.teams) == 2
        names = {s.name for s in resp.teams}
        assert names == {"alpha", "beta"}
        for summary in resp.teams:
            assert summary.agent_count == 3
            assert summary.total_cost_usd == 1.23

    def test_fallback_summaries_without_teams(self) -> None:
        """When no teams are provided, one stub summary is created per team_id."""
        t = _make_tournament(team_ids=[uuid4(), uuid4()])
        resp = _tournament_to_response(t)

        assert len(resp.teams) == 2
        for s in resp.teams:
            assert s.agent_count == 0
            assert s.total_cost_usd == 0.0

    def test_optional_fields_passed_through(self) -> None:
        """started_at, completed_at, and winner_team_id propagate correctly."""
        now = datetime.now(tz=timezone.utc)
        winner = uuid4()
        t = _make_tournament(phase=TournamentPhase.COMPLETE)
        t = t.model_copy(
            update={
                "started_at": now,
                "completed_at": now,
                "winner_team_id": winner,
            }
        )

        resp = _tournament_to_response(t)

        assert resp.started_at == now
        assert resp.completed_at == now
        assert resp.winner_team_id == winner

    def test_returns_tournament_response_type(self) -> None:
        """Return value is always a TournamentResponse instance."""
        t = _make_tournament()
        resp = _tournament_to_response(t)
        assert isinstance(resp, TournamentResponse)


# ============================================================
# POST /api/v1/tournaments — create_tournament
# ============================================================

class TestCreateTournament:
    """Tests for POST /tournaments."""

    def test_create_tournament_returns_201_on_success(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Valid config → orchestrator called → 201 with tournament body."""
        new_tournament = _make_tournament()
        mock_orchestrator.create_tournament.return_value = new_tournament

        payload = _make_tournament_config().model_dump(mode="json")
        response = client.post("/api/v1/tournaments", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert body["id"] == str(new_tournament.id)
        assert body["format"] == new_tournament.format.value
        assert body["current_phase"] == new_tournament.current_phase.value

    def test_create_tournament_calls_orchestrator_with_config(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """The orchestrator receives a TournamentConfig with correct values."""
        new_tournament = _make_tournament()
        mock_orchestrator.create_tournament.return_value = new_tournament

        payload = _make_tournament_config().model_dump(mode="json")
        client.post("/api/v1/tournaments", json=payload)

        mock_orchestrator.create_tournament.assert_awaited_once()
        passed_config: TournamentConfig = mock_orchestrator.create_tournament.call_args[0][0]
        assert isinstance(passed_config, TournamentConfig)
        assert passed_config.format == TournamentFormat.DUEL

    def test_create_tournament_returns_400_on_value_error(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Orchestrator raises ValueError → 400 with detail message."""
        mock_orchestrator.create_tournament.side_effect = ValueError("challenge not found")

        payload = _make_tournament_config().model_dump(mode="json")
        response = client.post("/api/v1/tournaments", json=payload)

        assert response.status_code == 400
        assert "challenge not found" in response.json()["detail"]

    def test_create_tournament_returns_500_on_unexpected_error(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Orchestrator raises generic Exception → 500."""
        mock_orchestrator.create_tournament.side_effect = RuntimeError("db failure")

        payload = _make_tournament_config().model_dump(mode="json")
        response = client.post("/api/v1/tournaments", json=payload)

        assert response.status_code == 500

    def test_create_tournament_returns_422_on_invalid_payload(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Malformed JSON payload → FastAPI 422 Unprocessable Entity."""
        response = client.post("/api/v1/tournaments", json={"format": "not_a_real_format"})

        assert response.status_code == 422


# ============================================================
# GET /api/v1/tournaments — list_tournaments
# ============================================================

class TestListTournaments:
    """Tests for GET /tournaments."""

    def test_list_tournaments_returns_200_with_empty_list(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """No active tournaments → 200 with empty list."""
        response = client.get("/api/v1/tournaments")

        assert response.status_code == 200
        body = response.json()
        assert body["tournaments"] == []
        assert body["total"] == 0

    def test_list_tournaments_returns_all_active(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Active tournaments are included in the response."""
        t1 = _make_tournament()
        t2 = _make_tournament(phase=TournamentPhase.BUILD)
        mock_orchestrator._active_tournaments = {t1.id: t1, t2.id: t2}

        response = client.get("/api/v1/tournaments")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert len(body["tournaments"]) == 2

    def test_list_tournaments_respects_limit(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """limit query param caps returned results."""
        tournaments = {uuid4(): _make_tournament() for _ in range(5)}
        mock_orchestrator._active_tournaments = tournaments

        response = client.get("/api/v1/tournaments?limit=2")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 5
        assert len(body["tournaments"]) == 2
        assert body["limit"] == 2

    def test_list_tournaments_respects_offset(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """offset query param skips earlier results."""
        tournaments = {uuid4(): _make_tournament() for _ in range(5)}
        mock_orchestrator._active_tournaments = tournaments

        response = client.get("/api/v1/tournaments?limit=10&offset=3")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 5
        assert len(body["tournaments"]) == 2  # 5 - 3 = 2 remaining
        assert body["offset"] == 3

    def test_list_tournaments_rejects_negative_offset(
        self,
        client: TestClient,
    ) -> None:
        """Negative offset → 422 validation error."""
        response = client.get("/api/v1/tournaments?offset=-1")
        assert response.status_code == 422

    def test_list_tournaments_rejects_limit_above_100(
        self,
        client: TestClient,
    ) -> None:
        """limit > 100 → 422 validation error."""
        response = client.get("/api/v1/tournaments?limit=101")
        assert response.status_code == 422


# ============================================================
# GET /api/v1/tournaments/{id} — get_tournament
# ============================================================

class TestGetTournament:
    """Tests for GET /tournaments/{id}."""

    def test_get_tournament_returns_200_when_found(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Existing tournament UUID → 200 with full body."""
        t = _make_tournament()
        mock_orchestrator._active_tournaments = {t.id: t}

        response = client.get(f"/api/v1/tournaments/{t.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(t.id)
        assert body["challenge_id"] == t.challenge_id

    def test_get_tournament_returns_404_when_not_found(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Unknown UUID → 404."""
        response = client.get(f"/api/v1/tournaments/{uuid4()}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_tournament_returns_422_for_non_uuid(
        self,
        client: TestClient,
    ) -> None:
        """Non-UUID path segment → 422 Unprocessable Entity."""
        response = client.get("/api/v1/tournaments/not-a-uuid")
        assert response.status_code == 422


# ============================================================
# POST /api/v1/tournaments/{id}/start — start_tournament
# ============================================================

class TestStartTournament:
    """Tests for POST /tournaments/{id}/start."""

    def test_start_tournament_returns_200_on_success(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """PREP tournament + orchestrator success → 200 with updated phase."""
        t = _make_tournament(phase=TournamentPhase.PREP)
        mock_orchestrator._active_tournaments = {t.id: t}

        started = t.model_copy(update={"current_phase": TournamentPhase.RESEARCH})
        mock_orchestrator.start_tournament.return_value = started

        response = client.post(f"/api/v1/tournaments/{t.id}/start")

        assert response.status_code == 200
        body = response.json()
        assert body["current_phase"] == TournamentPhase.RESEARCH.value

    def test_start_tournament_returns_404_when_not_found(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Unknown tournament ID → 404, orchestrator NOT called."""
        response = client.post(f"/api/v1/tournaments/{uuid4()}/start")

        assert response.status_code == 404
        mock_orchestrator.start_tournament.assert_not_awaited()

    def test_start_tournament_returns_400_when_wrong_phase(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Tournament not in PREP → 400, orchestrator NOT called."""
        t = _make_tournament(phase=TournamentPhase.BUILD)
        mock_orchestrator._active_tournaments = {t.id: t}

        response = client.post(f"/api/v1/tournaments/{t.id}/start")

        assert response.status_code == 400
        assert "prep" in response.json()["detail"].lower()
        mock_orchestrator.start_tournament.assert_not_awaited()

    def test_start_tournament_returns_400_on_orchestrator_value_error(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Orchestrator raises ValueError after phase check passes → 400."""
        t = _make_tournament(phase=TournamentPhase.PREP)
        mock_orchestrator._active_tournaments = {t.id: t}
        mock_orchestrator.start_tournament.side_effect = ValueError("sandbox unavailable")

        response = client.post(f"/api/v1/tournaments/{t.id}/start")

        assert response.status_code == 400
        assert "sandbox unavailable" in response.json()["detail"]

    def test_start_tournament_returns_500_on_unexpected_error(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Orchestrator raises generic Exception → 500."""
        t = _make_tournament(phase=TournamentPhase.PREP)
        mock_orchestrator._active_tournaments = {t.id: t}
        mock_orchestrator.start_tournament.side_effect = RuntimeError("crash")

        response = client.post(f"/api/v1/tournaments/{t.id}/start")

        assert response.status_code == 500

    def test_start_tournament_calls_orchestrator_with_correct_id(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """The orchestrator receives the correct UUID."""
        t = _make_tournament(phase=TournamentPhase.PREP)
        mock_orchestrator._active_tournaments = {t.id: t}
        started = t.model_copy(update={"current_phase": TournamentPhase.RESEARCH})
        mock_orchestrator.start_tournament.return_value = started

        client.post(f"/api/v1/tournaments/{t.id}/start")

        mock_orchestrator.start_tournament.assert_awaited_once_with(t.id)


# ============================================================
# POST /api/v1/tournaments/{id}/cancel — cancel_tournament
# ============================================================

class TestCancelTournament:
    """Tests for POST /tournaments/{id}/cancel."""

    def test_cancel_tournament_returns_200_on_success(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Active tournament + orchestrator.cancel_tournament → 200."""
        t = _make_tournament(phase=TournamentPhase.BUILD)
        mock_orchestrator._active_tournaments = {t.id: t}
        cancelled = t.model_copy(update={"current_phase": TournamentPhase.CANCELLED})
        mock_orchestrator.cancel_tournament.return_value = cancelled

        response = client.post(f"/api/v1/tournaments/{t.id}/cancel")

        assert response.status_code == 200
        body = response.json()
        assert body["current_phase"] == TournamentPhase.CANCELLED.value

    def test_cancel_tournament_returns_404_when_not_found(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Unknown UUID → 404."""
        response = client.post(f"/api/v1/tournaments/{uuid4()}/cancel")

        assert response.status_code == 404
        mock_orchestrator.cancel_tournament.assert_not_awaited()

    def test_cancel_tournament_returns_400_when_already_complete(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """COMPLETE phase is terminal → 400."""
        t = _make_tournament(phase=TournamentPhase.COMPLETE)
        mock_orchestrator._active_tournaments = {t.id: t}

        response = client.post(f"/api/v1/tournaments/{t.id}/cancel")

        assert response.status_code == 400
        assert "terminal" in response.json()["detail"].lower()
        mock_orchestrator.cancel_tournament.assert_not_awaited()

    def test_cancel_tournament_returns_400_when_already_cancelled(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """CANCELLED phase is terminal → 400."""
        t = _make_tournament(phase=TournamentPhase.CANCELLED)
        mock_orchestrator._active_tournaments = {t.id: t}

        response = client.post(f"/api/v1/tournaments/{t.id}/cancel")

        assert response.status_code == 400
        mock_orchestrator.cancel_tournament.assert_not_awaited()

    def test_cancel_tournament_falls_back_when_no_cancel_method(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Orchestrator without cancel_tournament method → in-process phase update."""
        t = _make_tournament(phase=TournamentPhase.RESEARCH)
        mock_orchestrator._active_tournaments = {t.id: t}
        # Remove the cancel_tournament attribute to trigger fallback
        del mock_orchestrator.cancel_tournament

        response = client.post(f"/api/v1/tournaments/{t.id}/cancel")

        # Should still return 200 via the fallback path
        assert response.status_code == 200

    def test_cancel_tournament_returns_500_on_unexpected_error(
        self,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Orchestrator raises generic Exception during cancel → 500."""
        t = _make_tournament(phase=TournamentPhase.RESEARCH)
        mock_orchestrator._active_tournaments = {t.id: t}
        mock_orchestrator.cancel_tournament.side_effect = RuntimeError("crash")

        response = client.post(f"/api/v1/tournaments/{t.id}/cancel")

        assert response.status_code == 500

    @pytest.mark.parametrize("phase", [
        TournamentPhase.PREP,
        TournamentPhase.RESEARCH,
        TournamentPhase.ARCHITECTURE,
        TournamentPhase.BUILD,
        TournamentPhase.CROSS_REVIEW,
        TournamentPhase.FIX,
        TournamentPhase.JUDGE,
    ])
    def test_cancel_tournament_succeeds_for_non_terminal_phases(
        self,
        phase: TournamentPhase,
        client: TestClient,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Cancel succeeds for every non-terminal phase."""
        t = _make_tournament(phase=phase)
        mock_orchestrator._active_tournaments = {t.id: t}
        cancelled = t.model_copy(update={"current_phase": TournamentPhase.CANCELLED})
        mock_orchestrator.cancel_tournament.return_value = cancelled

        response = client.post(f"/api/v1/tournaments/{t.id}/cancel")

        assert response.status_code == 200
