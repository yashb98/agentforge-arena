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

    # ----- Service Layer Initialization -----

    # LLM Client (via LiteLLM proxy)
    from packages.shared.src.llm.client import LLMClient
    langfuse_instance = getattr(app.state, "langfuse", None)
    app.state.llm_client = LLMClient(langfuse=langfuse_instance)
    logger.info("LLM client initialized (proxy: %s)", settings.llm.litellm_proxy_url)

    # Sandbox Manager
    from packages.sandbox.src.docker.manager import SandboxManager
    app.state.sandbox_manager = SandboxManager()
    logger.info("Sandbox manager initialized")

    # Agent Team Manager (with memory factory support)
    from packages.agents.src.teams.manager import AgentTeamManager
    app.state.agent_manager = AgentTeamManager(
        event_bus=app.state.event_bus,
        redis=app.state.redis,
        llm_client=app.state.llm_client,
        memory_factory=None,  # Wire MemoryFactory when infra is provisioned
    )
    logger.info("Agent team manager initialized (memory: lazy per-team)")

    # Judge Service
    from packages.judge.src.scoring.service import JudgeService
    app.state.judge_service = JudgeService(
        event_bus=app.state.event_bus,
        sandbox_manager=app.state.sandbox_manager,
        llm_client=app.state.llm_client,
    )
    logger.info("Judge service initialized")

    # Tournament Orchestrator
    from packages.core.src.tournament.orchestrator import TournamentOrchestrator
    app.state.orchestrator = TournamentOrchestrator(
        event_bus=app.state.event_bus,
        sandbox_manager=app.state.sandbox_manager,
        agent_manager=app.state.agent_manager,
        judge_service=app.state.judge_service,
    )
    logger.info("Tournament orchestrator initialized")

    yield

    # Shutdown
    logger.info("Shutting down AgentForge Arena")

    if hasattr(app.state, "agent_manager"):
        await app.state.agent_manager.teardown_all()

    if hasattr(app.state, "sandbox_manager"):
        await app.state.sandbox_manager.destroy_all()

    if hasattr(app.state, "llm_client"):
        await app.state.llm_client.close()

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
    from packages.api.src.routes.tournaments import router as tournaments_router
    from packages.api.src.routes.leaderboard import router as leaderboard_router
    from packages.api.src.routes.agents import router as agents_router
    from packages.api.src.routes.challenges import router as challenges_router

    # ---- Health Check (inline — no dependencies) ----
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

        # Database
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

    # ---- Mount Route Modules ----
    # tournaments.py has prefix="/tournaments" → mount at /api/v1
    app.include_router(tournaments_router, prefix="/api/v1")

    # leaderboard.py has prefix="/api/v1" baked in → mount at root
    app.include_router(leaderboard_router)

    # agents.py has prefix="/api/v1/tournaments" baked in → mount at root
    app.include_router(agents_router)

    # challenges.py has prefix="/api/v1" baked in → mount at root
    app.include_router(challenges_router)


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
