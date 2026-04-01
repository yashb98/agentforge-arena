"""
AgentForge Arena — Tournament Orchestrator

The master coordinator for tournament lifecycle. Manages phase transitions,
timing, sandbox provisioning, agent spawning, and judging invocation.

This is the most critical module in the system. Every tournament flows through here.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from packages.shared.src.config import get_settings
from packages.shared.src.db.base import get_session
from packages.shared.src.db.models import TournamentDB, TeamDB
from packages.shared.src.events.bus import EventBus
from packages.shared.src.types.models import (
    ArenaEvent,
    Tournament,
    TournamentConfig,
    TournamentFormat,
    TournamentPhase,
)

logger = logging.getLogger(__name__)


# Default phase durations in seconds
DEFAULT_PHASE_TIMINGS: dict[TournamentFormat, dict[TournamentPhase, int]] = {
    TournamentFormat.DUEL: {
        TournamentPhase.PREP: 300,           # 5 min
        TournamentPhase.RESEARCH: 1800,      # 30 min
        TournamentPhase.ARCHITECTURE: 900,    # 15 min
        TournamentPhase.BUILD: 5400,          # 90 min
        TournamentPhase.CROSS_REVIEW: 900,    # 15 min
        TournamentPhase.FIX: 900,             # 15 min
        TournamentPhase.JUDGE: 600,           # 10 min
    },
    TournamentFormat.STANDARD: {
        TournamentPhase.PREP: 300,
        TournamentPhase.RESEARCH: 1800,
        TournamentPhase.ARCHITECTURE: 900,
        TournamentPhase.BUILD: 4500,          # 75 min
        TournamentPhase.CROSS_REVIEW: 900,
        TournamentPhase.FIX: 900,
        TournamentPhase.JUDGE: 900,
    },
    TournamentFormat.LEAGUE: {
        TournamentPhase.PREP: 600,
        TournamentPhase.RESEARCH: 1800,
        TournamentPhase.ARCHITECTURE: 900,
        TournamentPhase.BUILD: 3600,          # 60 min
        TournamentPhase.CROSS_REVIEW: 600,
        TournamentPhase.FIX: 600,
        TournamentPhase.JUDGE: 1200,
    },
    TournamentFormat.GRAND_PRIX: {
        TournamentPhase.PREP: 600,
        TournamentPhase.RESEARCH: 1200,       # 20 min
        TournamentPhase.ARCHITECTURE: 600,
        TournamentPhase.BUILD: 2700,          # 45 min
        TournamentPhase.CROSS_REVIEW: 600,
        TournamentPhase.FIX: 600,
        TournamentPhase.JUDGE: 900,
    },
}

# Valid phase transitions
PHASE_TRANSITIONS: dict[TournamentPhase, TournamentPhase] = {
    TournamentPhase.PREP: TournamentPhase.RESEARCH,
    TournamentPhase.RESEARCH: TournamentPhase.ARCHITECTURE,
    TournamentPhase.ARCHITECTURE: TournamentPhase.BUILD,
    TournamentPhase.BUILD: TournamentPhase.CROSS_REVIEW,
    TournamentPhase.CROSS_REVIEW: TournamentPhase.FIX,
    TournamentPhase.FIX: TournamentPhase.JUDGE,
    TournamentPhase.JUDGE: TournamentPhase.COMPLETE,
}


class TournamentOrchestrator:
    """Manages the full tournament lifecycle."""

    def __init__(
        self,
        event_bus: EventBus,
        sandbox_manager: object,  # SandboxManager — imported at runtime to avoid circular
        agent_manager: object,    # AgentTeamManager
        judge_service: object,    # JudgeService
    ) -> None:
        self._events = event_bus
        self._sandbox = sandbox_manager
        self._agents = agent_manager
        self._judge = judge_service
        self._active_tournaments: dict[UUID, Tournament] = {}
        self._phase_timers: dict[UUID, asyncio.Task[None]] = {}
        self._health_tasks: dict[UUID, asyncio.Task[None]] = {}

    # ========================================================
    # Tournament Lifecycle
    # ========================================================

    async def create_tournament(self, config: TournamentConfig) -> Tournament:
        """Create a new tournament from configuration."""
        settings = get_settings()

        # Validate budget
        if config.budget_limit_usd > settings.llm.budget_per_tournament_usd:
            msg = (
                f"Budget {config.budget_limit_usd} exceeds max "
                f"{settings.llm.budget_per_tournament_usd}"
            )
            raise ValueError(msg)

        # Determine challenge
        challenge_id = config.challenge_id or await self._select_random_challenge()

        # Calculate rounds
        total_rounds = self._calculate_rounds(config.format, len(config.teams))

        tournament = Tournament(
            id=uuid4(),
            format=config.format,
            challenge_id=challenge_id,
            config=config,
            total_rounds=total_rounds,
        )

        # Persist to database
        async with get_session() as session:
            db_tournament = TournamentDB(
                id=tournament.id,
                format=tournament.format.value,
                current_phase=tournament.current_phase.value,
                challenge_id=challenge_id,
                config=config.model_dump(mode="json"),
                total_rounds=total_rounds,
            )
            session.add(db_tournament)

        # Publish creation event
        await self._events.publish(
            "tournament.created",
            source="core.orchestrator",
            tournament_id=tournament.id,
            payload={
                "format": config.format.value,
                "challenge_id": challenge_id,
                "team_count": len(config.teams),
            },
        )

        self._active_tournaments[tournament.id] = tournament
        logger.info("Tournament %s created: %s format, %d teams",
                     tournament.id, config.format.value, len(config.teams))

        return tournament

    async def start_tournament(self, tournament_id: UUID) -> Tournament:
        """Start a created tournament — provision sandboxes and spawn agents."""
        tournament = self._active_tournaments.get(tournament_id)
        if not tournament:
            msg = f"Tournament {tournament_id} not found"
            raise ValueError(msg)

        if tournament.current_phase != TournamentPhase.PREP:
            msg = f"Tournament is in phase {tournament.current_phase}, expected PREP"
            raise ValueError(msg)

        tournament.started_at = datetime.utcnow()

        # 1. Provision sandboxes for each team
        for i, team_config in enumerate(tournament.config.teams):
            team_id = uuid4()
            sandbox_id = await self._sandbox.create_sandbox(  # type: ignore[attr-defined]
                team_id=str(team_id),
                memory=team_config.sandbox_memory,
                cpus=team_config.sandbox_cpus,
            )

            # 2. Spawn agent team
            agent_ids = await self._agents.spawn_team(  # type: ignore[attr-defined]
                team_id=team_id,
                tournament_id=tournament_id,
                config=team_config,
                sandbox_id=sandbox_id,
            )

            tournament.team_ids.append(team_id)

            # Persist team
            async with get_session() as session:
                db_team = TeamDB(
                    id=team_id,
                    tournament_id=tournament_id,
                    name=team_config.name,
                    config=team_config.model_dump(mode="json"),
                    sandbox_id=sandbox_id,
                )
                session.add(db_team)

            await self._events.publish(
                "tournament.team.spawned",
                source="core.orchestrator",
                tournament_id=tournament_id,
                team_id=team_id,
                payload={
                    "team_name": team_config.name,
                    "sandbox_id": sandbox_id,
                    "agent_count": len(agent_ids),
                },
            )

        # 3. Deliver challenge to sandboxes
        await self._deliver_challenge(tournament)

        # 4. Start the phase timer
        await self._transition_phase(tournament, TournamentPhase.RESEARCH)

        # 5. Start health monitoring
        self._health_tasks[tournament_id] = asyncio.create_task(
            self._health_monitor(tournament)
        )

        await self._events.publish(
            "tournament.started",
            source="core.orchestrator",
            tournament_id=tournament_id,
            payload={"team_ids": [str(t) for t in tournament.team_ids]},
        )

        logger.info("Tournament %s started with %d teams",
                     tournament_id, len(tournament.team_ids))
        return tournament

    # ========================================================
    # Phase Management
    # ========================================================

    async def _transition_phase(
        self, tournament: Tournament, next_phase: TournamentPhase
    ) -> None:
        """Transition to the next phase with timing enforcement."""
        previous = tournament.current_phase

        # Validate transition
        if previous != TournamentPhase.PREP:
            expected_next = PHASE_TRANSITIONS.get(previous)
            if expected_next != next_phase:
                msg = f"Invalid transition: {previous} → {next_phase} (expected {expected_next})"
                raise ValueError(msg)

        tournament.current_phase = next_phase

        # Update database
        async with get_session() as session:
            result = await session.execute(
                TournamentDB.__table__.update()  # type: ignore[union-attr]
                .where(TournamentDB.id == tournament.id)
                .values(current_phase=next_phase.value, updated_at=datetime.utcnow())
            )

        # Publish phase change event
        await self._events.publish(
            "tournament.phase.changed",
            source="core.orchestrator",
            tournament_id=tournament.id,
            payload={
                "previous_phase": previous.value,
                "current_phase": next_phase.value,
            },
        )

        # Set timer for next transition
        if next_phase not in (TournamentPhase.COMPLETE, TournamentPhase.CANCELLED):
            timings = (
                tournament.config.phase_timings
                or DEFAULT_PHASE_TIMINGS[tournament.format]
            )
            duration = timings.get(next_phase, 3600)

            # Cancel existing timer
            if tournament.id in self._phase_timers:
                self._phase_timers[tournament.id].cancel()

            self._phase_timers[tournament.id] = asyncio.create_task(
                self._phase_timer(tournament, next_phase, duration)
            )

        logger.info("Tournament %s: %s → %s", tournament.id, previous.value, next_phase.value)

        # Execute phase-specific setup
        await self._execute_phase_setup(tournament, next_phase)

    async def _phase_timer(
        self, tournament: Tournament, phase: TournamentPhase, duration_seconds: int
    ) -> None:
        """Timer that enforces phase deadlines."""
        try:
            # Send 60-second warning
            if duration_seconds > 60:
                await asyncio.sleep(duration_seconds - 60)
                await self._events.publish(
                    "tournament.phase.ending",
                    source="core.orchestrator",
                    tournament_id=tournament.id,
                    payload={"phase": phase.value, "seconds_remaining": 60},
                )
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(duration_seconds)

            # Force transition
            next_phase = PHASE_TRANSITIONS.get(phase)
            if next_phase and tournament.current_phase == phase:
                logger.info("Phase %s timed out for tournament %s", phase.value, tournament.id)
                await self._transition_phase(tournament, next_phase)

        except asyncio.CancelledError:
            pass

    async def _execute_phase_setup(
        self, tournament: Tournament, phase: TournamentPhase
    ) -> None:
        """Execute phase-specific initialization logic."""
        match phase:
            case TournamentPhase.RESEARCH:
                # Notify agents: "Research phase started, challenge is in your workspace"
                for team_id in tournament.team_ids:
                    await self._notify_team(
                        tournament.id, team_id, "research_start",
                        {"message": "Research phase started. Read the challenge and research!"}
                    )

            case TournamentPhase.ARCHITECTURE:
                for team_id in tournament.team_ids:
                    await self._notify_team(
                        tournament.id, team_id, "architecture_start",
                        {"message": "Architecture phase. Create ARCHITECTURE.md and assign tasks."}
                    )

            case TournamentPhase.BUILD:
                for team_id in tournament.team_ids:
                    await self._notify_team(
                        tournament.id, team_id, "build_start",
                        {"message": "BUILD SPRINT! All agents work in parallel. Ship it!"}
                    )

            case TournamentPhase.CROSS_REVIEW:
                await self._setup_cross_review(tournament)

            case TournamentPhase.FIX:
                for team_id in tournament.team_ids:
                    await self._notify_team(
                        tournament.id, team_id, "fix_start",
                        {"message": "Fix phase. Address cross-review feedback. Last chance!"}
                    )

            case TournamentPhase.JUDGE:
                await self._invoke_judging(tournament)

            case TournamentPhase.COMPLETE:
                await self._complete_tournament(tournament)

    # ========================================================
    # Phase-Specific Logic
    # ========================================================

    async def _deliver_challenge(self, tournament: Tournament) -> None:
        """Copy challenge brief into each team's sandbox."""
        # Load challenge from DB/library
        challenge_brief = await self._load_challenge(tournament.challenge_id)

        for team_id in tournament.team_ids:
            await self._sandbox.write_file(  # type: ignore[attr-defined]
                team_id=str(team_id),
                path="CHALLENGE.md",
                content=challenge_brief,
            )

    async def _setup_cross_review(self, tournament: Tournament) -> None:
        """Grant read-only cross-team access for the review phase."""
        teams = tournament.team_ids
        for i, team_id in enumerate(teams):
            # Each team reviews the next team (circular)
            opponent_id = teams[(i + 1) % len(teams)]
            await self._sandbox.grant_read_access(  # type: ignore[attr-defined]
                reviewer_team=str(team_id),
                target_team=str(opponent_id),
            )
            await self._notify_team(
                tournament.id, team_id, "cross_review_start",
                {"opponent_team_id": str(opponent_id),
                 "message": "Cross-review started. Review opponent's code (read-only)."}
            )

    async def _invoke_judging(self, tournament: Tournament) -> None:
        """Trigger the judging pipeline."""
        await self._judge.judge_tournament(  # type: ignore[attr-defined]
            tournament_id=tournament.id,
            team_ids=tournament.team_ids,
            challenge_id=tournament.challenge_id,
        )

    async def _complete_tournament(self, tournament: Tournament) -> None:
        """Finalize tournament, update ELO, cleanup sandboxes."""
        tournament.completed_at = datetime.utcnow()

        # Cleanup sandboxes
        for team_id in tournament.team_ids:
            await self._sandbox.destroy_sandbox(str(team_id))  # type: ignore[attr-defined]

        # Cancel health monitor
        if tournament.id in self._health_tasks:
            self._health_tasks[tournament.id].cancel()

        await self._events.publish(
            "tournament.completed",
            source="core.orchestrator",
            tournament_id=tournament.id,
            payload={
                "winner_team_id": str(tournament.winner_team_id) if tournament.winner_team_id else None,
                "total_cost_usd": tournament.total_cost_usd,
                "duration_minutes": (
                    (tournament.completed_at - tournament.started_at).total_seconds() / 60
                    if tournament.started_at
                    else 0
                ),
            },
        )

        logger.info("Tournament %s completed. Winner: %s",
                     tournament.id, tournament.winner_team_id)

    # ========================================================
    # Health Monitoring
    # ========================================================

    async def _health_monitor(self, tournament: Tournament) -> None:
        """Monitor agent health every 30 seconds during active phases."""
        try:
            while tournament.current_phase not in (
                TournamentPhase.COMPLETE,
                TournamentPhase.CANCELLED,
            ):
                for team_id in tournament.team_ids:
                    health = await self._agents.check_team_health(  # type: ignore[attr-defined]
                        team_id=team_id
                    )
                    if not health["all_responsive"]:
                        for agent_info in health.get("unresponsive", []):
                            logger.warning(
                                "Agent %s in team %s is unresponsive",
                                agent_info["role"], team_id,
                            )
                            await self._events.publish(
                                "tournament.agent.unresponsive",
                                source="core.orchestrator",
                                tournament_id=tournament.id,
                                team_id=team_id,
                                payload=agent_info,
                            )

                # Check budget
                await self._check_budget(tournament)

                await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass

    async def _check_budget(self, tournament: Tournament) -> None:
        """Check if tournament is approaching budget limit."""
        settings = get_settings()
        threshold = tournament.config.budget_limit_usd * settings.llm.budget_alert_threshold

        if tournament.total_cost_usd >= threshold:
            await self._events.publish(
                "tournament.budget.warning",
                source="core.orchestrator",
                tournament_id=tournament.id,
                payload={
                    "current_cost": tournament.total_cost_usd,
                    "budget_limit": tournament.config.budget_limit_usd,
                    "percentage": tournament.total_cost_usd / tournament.config.budget_limit_usd,
                },
            )

    # ========================================================
    # Cancellation
    # ========================================================

    async def cancel_tournament(self, tournament_id: UUID) -> Tournament:
        """Cancel an active tournament, releasing all resources."""
        tournament = self._active_tournaments.get(tournament_id)
        if not tournament:
            msg = f"Tournament {tournament_id} not found"
            raise ValueError(msg)

        # Cancel phase timer
        if tournament_id in self._phase_timers:
            self._phase_timers[tournament_id].cancel()
            del self._phase_timers[tournament_id]

        # Cancel health monitor
        if tournament_id in self._health_tasks:
            self._health_tasks[tournament_id].cancel()
            del self._health_tasks[tournament_id]

        # Teardown sandboxes
        for team_id in tournament.team_ids:
            try:
                await self._sandbox.destroy_sandbox(str(team_id))  # type: ignore[attr-defined]
            except Exception:
                logger.warning("Failed to destroy sandbox for team %s", team_id)

        tournament.current_phase = TournamentPhase.CANCELLED
        tournament.completed_at = datetime.utcnow()

        # Persist
        async with get_session() as session:
            await session.execute(
                TournamentDB.__table__.update()  # type: ignore[union-attr]
                .where(TournamentDB.id == tournament_id)
                .values(
                    current_phase=TournamentPhase.CANCELLED.value,
                    completed_at=tournament.completed_at,
                    updated_at=datetime.utcnow(),
                )
            )

        await self._events.publish(
            "tournament.cancelled",
            source="core.orchestrator",
            tournament_id=tournament_id,
            payload={
                "previous_phase": tournament.current_phase.value,
                "team_count": len(tournament.team_ids),
            },
        )

        logger.info("Tournament %s cancelled", tournament_id)
        return tournament

    # ========================================================
    # Helpers
    # ========================================================

    async def _notify_team(
        self, tournament_id: UUID, team_id: UUID, event_type: str, data: dict
    ) -> None:
        """Send a notification to all agents in a team."""
        await self._events.publish(
            f"tournament.team.{event_type}",
            source="core.orchestrator",
            tournament_id=tournament_id,
            team_id=team_id,
            payload=data,
        )

    async def _select_random_challenge(self) -> str:
        """Select a random challenge from the library."""
        import random
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[4]
        library_dir = repo_root / "challenges" / "library"

        if not library_dir.is_dir():
            logger.warning("Challenge library not found at %s", library_dir)
            return "url-shortener-saas"

        challenges = [
            d.name for d in library_dir.iterdir()
            if d.is_dir() and (d / "CHALLENGE.md").is_file()
        ]

        if not challenges:
            return "url-shortener-saas"

        selected = random.choice(challenges)
        logger.info("Selected random challenge: %s", selected)
        return selected

    async def _load_challenge(self, challenge_id: str) -> str:
        """Load challenge brief markdown from the library."""
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[4]
        challenge_file = repo_root / "challenges" / "library" / challenge_id / "CHALLENGE.md"

        if not challenge_file.is_file():
            logger.error("Challenge file not found: %s", challenge_file)
            return f"# Challenge: {challenge_id}\n\nChallenge brief not found."

        return challenge_file.read_text(encoding="utf-8")

    def _calculate_rounds(self, format: TournamentFormat, team_count: int) -> int:
        """Calculate total rounds for a tournament format."""
        match format:
            case TournamentFormat.DUEL:
                return 1
            case TournamentFormat.STANDARD:
                # Single elimination: log2(teams)
                import math
                return max(1, int(math.log2(team_count)))
            case TournamentFormat.LEAGUE:
                # Round-robin: each team plays every other
                return team_count - 1
            case TournamentFormat.GRAND_PRIX:
                # Swiss system: ~log2(teams) + 1
                import math
                return max(3, int(math.log2(team_count)) + 1)
