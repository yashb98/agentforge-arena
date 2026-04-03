"""
AgentForge Arena — Tournament Orchestrator

The master coordinator for tournament lifecycle. Manages phase transitions,
timing, sandbox provisioning, agent spawning, and judging invocation.

This is the most critical module in the system. Every tournament flows through here.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from packages.core.src.tournament.quality_runner import QualityRunner
from packages.shared.src.challenge_library import load_validated_library_challenge
from packages.shared.src.config import get_settings
from packages.shared.src.db.base import get_session
from packages.shared.src.db.models import TeamDB, TournamentDB
from packages.shared.src.types.models import (
    Tournament,
    TournamentConfig,
    TournamentFormat,
    TournamentPhase,
)

if TYPE_CHECKING:
    from packages.shared.src.events.bus import EventBus

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
    # Reference timings only — MARATHON never auto-schedules these timers
    TournamentFormat.MARATHON: {
        TournamentPhase.PREP: 86400,
        TournamentPhase.RESEARCH: 86400 * 3,
        TournamentPhase.ARCHITECTURE: 86400,
        TournamentPhase.BUILD: 86400 * 7,
        TournamentPhase.CROSS_REVIEW: 86400,
        TournamentPhase.FIX: 86400,
        TournamentPhase.JUDGE: 86400,
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


def _uses_auto_phase_timers(fmt: TournamentFormat) -> bool:
    """Marathon format uses milestone API instead of wall-clock phase timers."""
    return fmt != TournamentFormat.MARATHON


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
        self._team_hierarchy: dict[UUID, dict[UUID, list[UUID]]] = {}

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

        self._validate_challenge_library_entry(challenge_id)
        self._validate_team_names(config)

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
        settings = get_settings()
        resource_profile = await self._load_challenge_resource_profile(tournament)

        # 1. Provision sandboxes for each team
        team_id_to_name: dict[UUID, str] = {}
        team_name_to_id: dict[str, UUID] = {}
        team_id_to_parent_name: dict[UUID, str] = {}
        for team_config in tournament.config.teams:
            team_id = uuid4()
            memory, cpus = self._resolve_team_sandbox_resources(
                team_memory=team_config.sandbox_memory,
                team_cpus=team_config.sandbox_cpus,
                default_memory=settings.sandbox.default_memory,
                default_cpus=settings.sandbox.default_cpus,
                profile=resource_profile,
            )
            sandbox_id = await self._sandbox.create_sandbox(  # type: ignore[attr-defined]
                team_id=str(team_id),
                memory=memory,
                cpus=cpus,
            )

            # 2. Spawn agent team
            agent_ids = await self._agents.spawn_team(  # type: ignore[attr-defined]
                team_id=team_id,
                tournament_id=tournament_id,
                config=team_config,
                sandbox_id=sandbox_id,
            )

            tournament.team_ids.append(team_id)
            team_id_to_name[team_id] = team_config.name
            team_name_to_id[team_config.name] = team_id
            if team_config.parent_team_name:
                team_id_to_parent_name[team_id] = team_config.parent_team_name

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

        hierarchy = self._resolve_team_hierarchy(
            team_name_to_id=team_name_to_id,
            team_id_to_name=team_id_to_name,
            team_id_to_parent_name=team_id_to_parent_name,
        )
        if hierarchy:
            self._team_hierarchy[tournament_id] = hierarchy
            for parent_id, children in hierarchy.items():
                for child_id in children:
                    await self._events.publish(
                        "tournament.team.hierarchy.linked",
                        source="core.orchestrator",
                        tournament_id=tournament_id,
                        team_id=child_id,
                        payload={
                            "parent_team_id": str(parent_id),
                            "child_team_id": str(child_id),
                        },
                    )
            setter = getattr(self._agents, "set_team_hierarchy", None)
            if callable(setter):
                maybe_result = setter(
                    tournament_id=tournament_id,
                    hierarchy=hierarchy,
                )
                if asyncio.iscoroutine(maybe_result):
                    await maybe_result

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
            await session.execute(
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

        # Set timer for next transition (skipped for MARATHON — milestones only)
        if next_phase not in (TournamentPhase.COMPLETE, TournamentPhase.CANCELLED):
            timings = (
                tournament.config.phase_timings
                or DEFAULT_PHASE_TIMINGS[tournament.format]
            )
            duration = timings.get(next_phase, 3600)

            # Cancel existing timer
            if tournament.id in self._phase_timers:
                self._phase_timers[tournament.id].cancel()
                del self._phase_timers[tournament.id]

            if _uses_auto_phase_timers(tournament.format):
                await self._persist_runtime_checkpoint(
                    tournament, timer_phase=next_phase, duration_seconds=duration
                )
                self._phase_timers[tournament.id] = asyncio.create_task(
                    self._phase_timer(tournament, next_phase, duration)
                )
            else:
                await self._persist_runtime_checkpoint(
                    tournament, timer_phase=None, duration_seconds=0
                )

        logger.info("Tournament %s: %s → %s", tournament.id, previous.value, next_phase.value)

        # Execute phase-specific setup
        await self._execute_phase_setup(tournament, next_phase)

    async def _phase_timer(
        self,
        tournament: Tournament,
        phase: TournamentPhase,
        duration_seconds: int,
        *,
        resume_remaining_seconds: int | None = None,
    ) -> None:
        """Timer that enforces phase deadlines.

        When ``resume_remaining_seconds`` is set (after process restart), sleeps are
        based on remaining wall time instead of the full configured duration.
        """
        try:
            budget = (
                resume_remaining_seconds
                if resume_remaining_seconds is not None
                else duration_seconds
            )
            if budget <= 0:
                next_phase = PHASE_TRANSITIONS.get(phase)
                if next_phase and tournament.current_phase == phase:
                    await self._transition_phase(tournament, next_phase)
                return

            # Send 60-second warning when enough time remains
            if budget > 60:
                await asyncio.sleep(budget - 60)
                await self._events.publish(
                    "tournament.phase.ending",
                    source="core.orchestrator",
                    tournament_id=tournament.id,
                    payload={"phase": phase.value, "seconds_remaining": 60},
                )
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(budget)

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
                await self._run_quality_pipeline(tournament, trigger="phase_build")
                for team_id in tournament.team_ids:
                    await self._notify_team(
                        tournament.id, team_id, "build_start",
                        {"message": "BUILD SPRINT! All agents work in parallel. Ship it!"}
                    )

            case TournamentPhase.CROSS_REVIEW:
                await self._setup_cross_review(tournament)

            case TournamentPhase.FIX:
                await self._run_quality_pipeline(tournament, trigger="phase_fix")
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
        """Copy challenge brief and spec into each team's sandbox."""
        repo_root = Path(__file__).resolve().parents[4]
        spec_json: str | None = None
        try:
            md, spec = load_validated_library_challenge(repo_root, tournament.challenge_id)
            spec_json = json.dumps(spec.model_dump(mode="json"), indent=2)
        except (FileNotFoundError, ValidationError, ValueError, OSError):
            logger.exception(
                "Validated challenge bundle missing for %s; delivering markdown only",
                tournament.challenge_id,
            )
            md = await self._load_challenge(tournament.challenge_id)

        for team_id in tournament.team_ids:
            await self._sandbox.write_file(  # type: ignore[attr-defined]
                team_id=str(team_id),
                path="CHALLENGE.md",
                content=md,
            )
            if spec_json is not None:
                await self._sandbox.write_file(  # type: ignore[attr-defined]
                    team_id=str(team_id),
                    path="challenge.spec.json",
                    content=spec_json,
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
        await self._clear_runtime_checkpoint(tournament.id)

        # Cleanup sandboxes
        for team_id in tournament.team_ids:
            await self._sandbox.destroy_sandbox(str(team_id))  # type: ignore[attr-defined]

        # Cancel health monitor
        if tournament.id in self._health_tasks:
            self._health_tasks[tournament.id].cancel()
        self._team_hierarchy.pop(tournament.id, None)

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
        self._team_hierarchy.pop(tournament_id, None)

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
                    runtime_state={},
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
    # Durability (P0 checkpoint / resume) & marathon milestones (P1)
    # ========================================================

    async def _persist_runtime_checkpoint(
        self,
        tournament: Tournament,
        *,
        timer_phase: TournamentPhase | None,
        duration_seconds: int,
    ) -> None:
        """Write ``runtime_state`` JSONB for crash recovery and timer restore."""
        payload: dict = {
            "total_cost_usd": tournament.total_cost_usd,
            "team_ids": [str(x) for x in tournament.team_ids],
            "checkpoint_version": 1,
        }
        if (
            timer_phase
            and duration_seconds > 0
            and _uses_auto_phase_timers(tournament.format)
        ):
            deadline = datetime.utcnow() + timedelta(seconds=duration_seconds)
            payload["phase_timer_phase"] = timer_phase.value
            payload["deadline_utc"] = deadline.isoformat()
            payload["duration_seconds"] = duration_seconds
        else:
            payload["phase_timer_phase"] = tournament.current_phase.value
            payload["deadline_utc"] = None
            payload["duration_seconds"] = 0
            payload["milestone_mode"] = not _uses_auto_phase_timers(tournament.format)

        async with get_session() as session:
            await session.execute(
                update(TournamentDB)
                .where(TournamentDB.id == tournament.id)
                .values(runtime_state=payload, updated_at=datetime.utcnow())
            )

    async def _clear_runtime_checkpoint(self, tournament_id: UUID) -> None:
        async with get_session() as session:
            await session.execute(
                update(TournamentDB)
                .where(TournamentDB.id == tournament_id)
                .values(runtime_state={}, updated_at=datetime.utcnow())
            )

    def _tournament_from_db_row(self, row: TournamentDB) -> Tournament:
        config = TournamentConfig.model_validate(row.config, strict=False)
        team_ids = [t.id for t in row.teams]
        return Tournament(
            id=row.id,
            format=TournamentFormat(row.format),
            current_phase=TournamentPhase(row.current_phase),
            challenge_id=row.challenge_id,
            config=config,
            team_ids=team_ids,
            current_round=row.current_round,
            total_rounds=row.total_rounds,
            started_at=row.started_at,
            completed_at=row.completed_at,
            winner_team_id=row.winner_team_id,
            total_cost_usd=row.total_cost_usd,
        )

    async def restore_durable_tournaments(self) -> None:
        """Reload non-terminal tournaments from PostgreSQL after API restart."""
        async with get_session() as session:
            result = await session.execute(
                select(TournamentDB)
                .options(selectinload(TournamentDB.teams))
                .where(
                    TournamentDB.current_phase.not_in(
                        [
                            TournamentPhase.COMPLETE.value,
                            TournamentPhase.CANCELLED.value,
                        ]
                    )
                )
            )
            rows = result.scalars().unique().all()

        for row in rows:
            tournament = self._tournament_from_db_row(row)
            self._active_tournaments[tournament.id] = tournament
            rs = row.runtime_state or {}
            if tournament.team_ids and tournament.current_phase != TournamentPhase.PREP:
                self._health_tasks[tournament.id] = asyncio.create_task(
                    self._health_monitor(tournament)
                )
            if not _uses_auto_phase_timers(tournament.format):
                logger.info(
                    "Restored tournament %s (marathon / no auto-timer)",
                    tournament.id,
                )
                continue
            deadline_raw = rs.get("deadline_utc")
            phase_key = rs.get("phase_timer_phase")
            duration_saved = int(rs.get("duration_seconds") or 0)
            if not deadline_raw or not phase_key:
                continue
            try:
                deadline = datetime.fromisoformat(str(deadline_raw))
            except ValueError:
                logger.warning("Bad deadline in runtime_state for %s", tournament.id)
                continue
            if phase_key != tournament.current_phase.value:
                logger.warning(
                    "Stale timer phase for tournament %s — skipping timer restore",
                    tournament.id,
                )
                continue
            remaining = (deadline - datetime.utcnow()).total_seconds()
            timings = (
                tournament.config.phase_timings
                or DEFAULT_PHASE_TIMINGS[tournament.format]
            )
            full_dur = timings.get(tournament.current_phase, duration_saved or 3600)
            if tournament.id in self._phase_timers:
                self._phase_timers[tournament.id].cancel()
            tp = tournament.current_phase
            resume_sec = int(remaining) if remaining > 0 else 1
            self._phase_timers[tournament.id] = asyncio.create_task(
                self._phase_timer(
                    tournament,
                    tp,
                    full_dur,
                    resume_remaining_seconds=resume_sec,
                )
            )
            logger.info(
                "Restored phase timer for tournament %s (~%.0fs left)",
                tournament.id,
                max(0, remaining),
            )

    async def checkpoint_tournament(self, tournament_id: UUID) -> Tournament:
        """Persist current tournament scalars; runtime_state updated on phase changes."""
        tournament = self._active_tournaments.get(tournament_id)
        if not tournament:
            msg = f"Tournament {tournament_id} not found in memory"
            raise ValueError(msg)
        async with get_session() as session:
            await session.execute(
                update(TournamentDB)
                .where(TournamentDB.id == tournament_id)
                .values(
                    current_phase=tournament.current_phase.value,
                    total_cost_usd=tournament.total_cost_usd,
                    winner_team_id=tournament.winner_team_id,
                    started_at=tournament.started_at,
                    completed_at=tournament.completed_at,
                    updated_at=datetime.utcnow(),
                )
            )
        await self._events.publish(
            "tournament.checkpointed",
            source="core.orchestrator",
            tournament_id=tournament_id,
            payload={"phase": tournament.current_phase.value},
        )
        return tournament

    async def advance_milestone(self, tournament_id: UUID) -> Tournament:
        """MARATHON only: move to the next phase without wall-clock timers."""
        tournament = self._active_tournaments.get(tournament_id)
        if not tournament:
            msg = f"Tournament {tournament_id} not found"
            raise ValueError(msg)
        if tournament.format != TournamentFormat.MARATHON:
            msg = "advance_milestone is only valid for marathon format tournaments"
            raise ValueError(msg)
        if tournament.current_phase in (
            TournamentPhase.COMPLETE,
            TournamentPhase.CANCELLED,
        ):
            msg = f"Tournament {tournament_id} is already terminal"
            raise ValueError(msg)
        nxt = PHASE_TRANSITIONS.get(tournament.current_phase)
        if not nxt:
            msg = "No next phase from current state"
            raise ValueError(msg)
        await self._run_quality_pipeline(
            tournament,
            trigger=f"milestone:{tournament.current_phase.value}->{nxt.value}",
            fail_on_required=True,
        )
        await self._transition_phase(tournament, nxt)
        return tournament

    async def _run_quality_pipeline(
        self,
        tournament: Tournament,
        *,
        trigger: str,
        fail_on_required: bool = False,
    ) -> None:
        """Execute challenge quality commands and optionally gate progress."""
        repo_root = Path(__file__).resolve().parents[4]
        try:
            _, spec = load_validated_library_challenge(repo_root, tournament.challenge_id)
        except (FileNotFoundError, ValidationError, ValueError):
            logger.exception("Skipping quality pipeline: invalid challenge spec")
            return

        commands = spec.quality.commands
        if not commands:
            return

        runner = QualityRunner(self._sandbox, repo_root=repo_root)
        failures: list[dict[str, object]] = []
        for team_id in tournament.team_ids:
            await self._events.publish(
                "tournament.quality.started",
                source="core.orchestrator",
                tournament_id=tournament.id,
                team_id=team_id,
                payload={"trigger": trigger, "command_count": len(commands)},
            )
            result = await runner.run_for_team(team_id=str(team_id), commands=commands)
            payload = {
                "trigger": trigger,
                "passed": result.passed,
                "commands": [
                    {
                        "name": r.name,
                        "required": r.required,
                        "returncode": r.returncode,
                        "passed": r.passed,
                    }
                    for r in result.command_results
                ],
            }
            await self._events.publish(
                "tournament.quality.passed" if result.passed else "tournament.quality.failed",
                source="core.orchestrator",
                tournament_id=tournament.id,
                team_id=team_id,
                payload=payload,
            )
            if not result.passed:
                failures.append({"team_id": str(team_id), "payload": payload})

        if fail_on_required and failures:
            msg = (
                "Quality gate failed for required command(s): "
                + ", ".join(f["team_id"] for f in failures)
            )
            raise ValueError(msg)

    async def hydrate_tournament_from_db(self, tournament_id: UUID) -> Tournament:
        """Load tournament from DB into memory if missing."""
        if tournament_id in self._active_tournaments:
            return self._active_tournaments[tournament_id]
        async with get_session() as session:
            result = await session.execute(
                select(TournamentDB)
                .options(selectinload(TournamentDB.teams))
                .where(TournamentDB.id == tournament_id)
            )
            row = result.scalar_one_or_none()
        if row is None:
            msg = f"Tournament {tournament_id} not found in database"
            raise ValueError(msg)
        tournament = self._tournament_from_db_row(row)
        self._active_tournaments[tournament_id] = tournament
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
            d.name
            for d in library_dir.iterdir()
            if d.is_dir()
            and (d / "CHALLENGE.md").is_file()
            and (d / "challenge.spec.json").is_file()
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

    def _validate_challenge_library_entry(self, challenge_id: str) -> None:
        """Require ``CHALLENGE.md`` + ``challenge.spec.json`` with matching metadata."""
        repo_root = Path(__file__).resolve().parents[4]
        try:
            load_validated_library_challenge(repo_root, challenge_id)
        except FileNotFoundError as e:
            msg = f"Challenge {challenge_id!r} missing library files: {e}"
            raise ValueError(msg) from e
        except ValidationError as e:
            msg = f"Invalid challenge.spec.json for {challenge_id!r}: {e}"
            raise ValueError(msg) from e
        except ValueError as e:
            msg = f"Challenge {challenge_id!r} spec out of sync with CHALLENGE.md: {e}"
            raise ValueError(msg) from e

    def _validate_team_names(self, config: TournamentConfig) -> None:
        names = [team.name for team in config.teams]
        if len(names) != len(set(names)):
            msg = "Team names must be unique for hierarchy routing"
            raise ValueError(msg)

    def _resolve_team_hierarchy(
        self,
        *,
        team_name_to_id: dict[str, UUID],
        team_id_to_name: dict[UUID, str],
        team_id_to_parent_name: dict[UUID, str],
    ) -> dict[UUID, list[UUID]]:
        hierarchy: dict[UUID, list[UUID]] = {}
        for child_id, parent_name in team_id_to_parent_name.items():
            parent_id = team_name_to_id.get(parent_name)
            if parent_id is None:
                msg = f"Unknown parent_team_name {parent_name!r}"
                raise ValueError(msg)
            if parent_id == child_id:
                child_name = team_id_to_name[child_id]
                msg = f"Team {child_name!r} cannot parent itself"
                raise ValueError(msg)
            hierarchy.setdefault(parent_id, []).append(child_id)
        return hierarchy

    def get_team_hierarchy(self, tournament_id: UUID) -> dict[UUID, list[UUID]]:
        return self._team_hierarchy.get(tournament_id, {})

    async def _load_challenge_resource_profile(self, tournament: Tournament) -> dict[str, object]:
        repo_root = Path(__file__).resolve().parents[4]
        try:
            _, spec = load_validated_library_challenge(repo_root, tournament.challenge_id)
        except (FileNotFoundError, ValidationError, ValueError):
            return {}

        by_phase = spec.resources.by_phase.get(TournamentPhase.PREP.value)
        if by_phase is not None:
            return {"memory": by_phase.memory, "cpus": by_phase.cpus}
        by_format = spec.resources.by_format.get(tournament.format.value)
        if by_format is not None:
            return {"memory": by_format.memory, "cpus": by_format.cpus}
        return {}

    def _resolve_team_sandbox_resources(
        self,
        *,
        team_memory: str,
        team_cpus: int,
        default_memory: str,
        default_cpus: int,
        profile: dict[str, object],
    ) -> tuple[str, int]:
        # Team-level explicit values always win; profile applies to defaults only.
        memory = team_memory
        cpus = team_cpus
        if team_memory == default_memory and isinstance(profile.get("memory"), str):
            memory = str(profile["memory"])
        if team_cpus == default_cpus and isinstance(profile.get("cpus"), int):
            cpus = int(profile["cpus"])
        return memory, cpus

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
            case TournamentFormat.MARATHON:
                return 1
