"""
AgentForge Arena — FastAPI Application

Main API entry point. Mounts all route modules, configures middleware,
and initializes service dependencies.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from packages.shared.src.config import get_settings
from packages.shared.src.db.base import close_db, init_db
from packages.shared.src.events.bus import EventBus

logger = logging.getLogger(__name__)


# ============================================================
# Lifespan — Startup / Shutdown
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize and cleanup resources."""
    settings = get_settings()

    # Startup
    logger.info("Starting AgentForge Arena v%s (%s)", settings.version, settings.environment)

    # Database
    await init_db()
    logger.info("Database initialized")

    # Redis
    app.state.redis = aioredis.from_url(
        settings.redis.url,
        decode_responses=False,
    )
    await app.state.redis.ping()
    logger.info("Redis connected")

    # Event Bus
    app.state.event_bus = EventBus(app.state.redis)
    logger.info("Event bus initialized")

    # Langfuse
    if settings.langfuse.enabled:
        try:
            from langfuse import Langfuse
            app.state.langfuse = Langfuse(
                public_key=settings.langfuse.public_key,
                secret_key=settings.langfuse.secret_key.get_secret_value(),
                host=settings.langfuse.host,
            )
            logger.info("Langfuse connected")
        except Exception:
            logger.warning("Langfuse initialization failed — tracing disabled")
            app.state.langfuse = None

    yield

    # Shutdown
    logger.info("Shutting down AgentForge Arena")
    if hasattr(app.state, "langfuse") and app.state.langfuse:
        app.state.langfuse.flush()
    if hasattr(app.state, "redis"):
        await app.state.redis.close()
    await close_db()


# ============================================================
# Application Factory
# ============================================================

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="AgentForge Arena API",
        description="Competitive tournament platform where AI agent teams build production apps",
        version=settings.version,
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routes
    _register_routes(app)

    return app


def _register_routes(app: FastAPI) -> None:
    """Register all API routes."""

    # ---- Health Check ----
    @app.get("/health", tags=["system"])
    async def health_check(request: Request) -> dict:
        """Check system health."""
        checks: dict[str, str] = {}

        # Redis
        try:
            await request.app.state.redis.ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {e}"

        # Database (simple check)
        try:
            from packages.shared.src.db.base import get_session
            async with get_session() as session:
                await session.execute("SELECT 1")  # type: ignore[arg-type]
            checks["database"] = "ok"
        except Exception as e:
            checks["database"] = f"error: {e}"

        all_ok = all(v == "ok" for v in checks.values())
        return {
            "status": "healthy" if all_ok else "degraded",
            "version": get_settings().version,
            "checks": checks,
        }

    # ---- Tournament Routes ----
    @app.post("/api/v1/tournaments", tags=["tournaments"])
    async def create_tournament(request: Request) -> dict:
        """Create a new tournament."""
        body = await request.json()

        from packages.shared.src.types.models import TournamentConfig
        config = TournamentConfig.model_validate(body)

        # TODO: Wire up TournamentOrchestrator via dependency injection
        return {
            "status": "created",
            "message": "Tournament creation endpoint — wire up orchestrator",
            "config": config.model_dump(mode="json"),
        }

    @app.get("/api/v1/tournaments", tags=["tournaments"])
    async def list_tournaments() -> dict:
        """List all tournaments."""
        return {"tournaments": [], "total": 0}

    @app.get("/api/v1/tournaments/{tournament_id}", tags=["tournaments"])
    async def get_tournament(tournament_id: str) -> dict:
        """Get tournament details."""
        return {"tournament_id": tournament_id, "status": "not_found"}

    @app.post("/api/v1/tournaments/{tournament_id}/start", tags=["tournaments"])
    async def start_tournament(tournament_id: str) -> dict:
        """Start a tournament."""
        return {"tournament_id": tournament_id, "action": "start"}

    # ---- Leaderboard Routes ----
    @app.get("/api/v1/leaderboard", tags=["leaderboard"])
    async def get_leaderboard(category: str = "overall") -> dict:
        """Get the ELO leaderboard."""
        return {"category": category, "entries": []}

    # ---- Challenge Routes ----
    @app.get("/api/v1/challenges", tags=["challenges"])
    async def list_challenges(category: str | None = None) -> dict:
        """List available challenges."""
        return {"challenges": [], "total": 0}

    @app.get("/api/v1/challenges/{challenge_id}", tags=["challenges"])
    async def get_challenge(challenge_id: str) -> dict:
        """Get challenge details."""
        return {"challenge_id": challenge_id, "status": "not_found"}

    # ---- Spectator Routes (WebSocket) ----
    @app.get("/api/v1/tournaments/{tournament_id}/spectate", tags=["spectator"])
    async def spectate_info(tournament_id: str) -> dict:
        """Get spectator connection info for a tournament."""
        return {
            "tournament_id": tournament_id,
            "websocket_url": f"/ws/spectate/{tournament_id}",
            "message": "Connect via WebSocket for real-time updates",
        }

    # ---- Replay Routes ----
    @app.get("/api/v1/tournaments/{tournament_id}/replay", tags=["replay"])
    async def get_replay(tournament_id: str) -> dict:
        """Get replay data for a completed tournament."""
        return {"tournament_id": tournament_id, "events": []}

    # ---- Agent Routes ----
    @app.get("/api/v1/tournaments/{tournament_id}/agents", tags=["agents"])
    async def list_agents(tournament_id: str) -> dict:
        """List all agents in a tournament."""
        return {"tournament_id": tournament_id, "agents": []}


# ============================================================
# Entry Point
# ============================================================

app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "packages.api.src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )
