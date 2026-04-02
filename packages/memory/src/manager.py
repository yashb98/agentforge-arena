"""MemoryManager — Single entry point for the 3-layer memory system."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from packages.memory.src.compression.compressor import ContextCompressor
from packages.memory.src.compression.doc_sync import DocumentSyncer
from packages.memory.src.compression.promoter import MemoryPromoter
from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.semantic.models import MemoryContext
from packages.memory.src.working.models import WorkingState
from packages.shared.src.types.models import AgentRole, TournamentPhase

logger = logging.getLogger(__name__)


class MemoryManager:
    """One per team. Each agent gets its own L1, shares L2/L3 with teammates.

    Two main methods:
        recall() — before each LLM call, gather context from all 3 layers
        record() — after each LLM call, persist what happened
    """

    def __init__(
        self,
        team_id: UUID,
        tournament_id: UUID,
        working_store: object,
        module_store: object,
        semantic_store: object,
        compressor: ContextCompressor,
        promoter: MemoryPromoter,
        doc_syncer: DocumentSyncer,
    ) -> None:
        self._team_id = team_id
        self._tournament_id = tournament_id
        self._working = working_store
        self._module = module_store
        self._semantic = semantic_store
        self._compressor = compressor
        self._promoter = promoter
        self._doc_syncer = doc_syncer

    async def recall(
        self,
        agent_id: UUID,
        role: AgentRole,
        query: str,
        *,
        max_working_tokens: int = 2000,
        max_module_results: int = 5,
        max_semantic_results: int = 10,
    ) -> MemoryContext:
        """Retrieve context from all 3 layers before an LLM call."""
        # L1: Read working state
        working_state = await self._working.load(role)  # type: ignore[union-attr]
        if working_state is None:
            working_state = WorkingState(
                agent_id=agent_id,
                team_id=self._team_id,
                role=role,
                current_phase=TournamentPhase.BUILD,
            )

        # Check for overflow before returning context
        if await self._working.exceeds_threshold(role, threshold=max_working_tokens):  # type: ignore[union-attr]
            await self._handle_overflow(agent_id, role)
            working_state = await self._working.load(role)  # type: ignore[union-attr]
            if working_state is None:
                working_state = WorkingState(
                    agent_id=agent_id,
                    team_id=self._team_id,
                    role=role,
                    current_phase=TournamentPhase.BUILD,
                )

        # L2: Query module memory (hybrid SQL + full-text)
        module_results = await self._module.search_fulltext(  # type: ignore[union-attr]
            query,
            limit=max_module_results,
        )

        # L3: Query semantic memory (Qdrant vector search)
        semantic_results = await self._semantic.search(  # type: ignore[union-attr]
            query,
            limit=max_semantic_results,
        )

        # Estimate total tokens
        total_tokens = working_state.estimate_tokens()
        for r in module_results:
            total_tokens += len(r.content) // 4
        for s in semantic_results:
            total_tokens += len(s.snippet) // 4

        return MemoryContext(
            working_state=working_state,
            module_context=module_results,
            semantic_context=semantic_results,
            total_tokens_estimate=total_tokens,
        )

    async def record(
        self,
        agent_id: UUID,
        role: AgentRole,
        *,
        task: str | None = None,
        file_touched: str | None = None,
        decision: str | None = None,
        error: str | None = None,
        error_resolved: str | None = None,
        action_summary: str | None = None,
        module_records: list[ModuleRecord] | None = None,
    ) -> None:
        """Record what happened after an LLM call."""
        # Load current state (or create fresh)
        state = await self._working.load(role)  # type: ignore[union-attr]
        if state is None:
            state = WorkingState(
                agent_id=agent_id,
                team_id=self._team_id,
                role=role,
                current_phase=TournamentPhase.BUILD,
            )

        # Update L1 fields
        updates: dict = {"last_updated": datetime.now(UTC)}
        if task is not None:
            updates["current_task"] = task
        if file_touched is not None:
            updates["current_file"] = file_touched
            files = list(state.recent_files_touched)
            files.append(file_touched)
            updates["recent_files_touched"] = files
        if decision is not None:
            decisions = list(state.recent_decisions)
            decisions.append(decision)
            updates["recent_decisions"] = decisions
        if error is not None:
            errors = list(state.active_errors)
            errors.append(error)
            updates["active_errors"] = errors
        if error_resolved is not None:
            errors = [e for e in state.active_errors if error_resolved not in e]
            updates["active_errors"] = errors

        updated_state = state.model_copy(update=updates)
        await self._working.save(updated_state)  # type: ignore[union-attr]

        # Persist module records to L2
        if module_records:
            await self._module.insert_batch(module_records)  # type: ignore[union-attr]

        # Log action to L2
        if action_summary:
            log_record = ModuleRecord(
                team_id=self._team_id,
                tournament_id=self._tournament_id,
                record_type=RecordType.ACTION_LOG,
                module_name="general",
                title=action_summary[:200],
                content=action_summary,
                agent_id=agent_id,
                agent_role=role,
            )
            await self._module.insert(log_record)  # type: ignore[union-attr]

    async def _handle_overflow(self, agent_id: UUID, role: AgentRole) -> None:
        """Compress + Promote + Doc Sync when L1 exceeds threshold."""
        state = await self._working.load(role)  # type: ignore[union-attr]
        if state is None:
            return

        # 1. Promote important items from L1 to L2
        promoted_records = self._promoter.promote(
            state,
            tournament_id=self._tournament_id,
        )
        if promoted_records:
            await self._module.insert_batch(promoted_records)  # type: ignore[union-attr]

        # 2. Compress L1 via Haiku
        compressed = await self._compressor.compress(state)
        updated_state = self._compressor.apply(state, compressed)
        await self._working.save(updated_state)  # type: ignore[union-attr]

        # 3. Sync new records to .md files
        if promoted_records:
            synced_ids = self._doc_syncer.sync(promoted_records)
            if synced_ids:
                await self._module.mark_synced(synced_ids)  # type: ignore[union-attr]

        logger.info(
            "Overflow handled for %s: promoted=%d, dropped=%d",
            role.value,
            len(promoted_records),
            compressed.dropped_count,
        )

    async def initialize(self, agent_id: UUID, role: AgentRole) -> None:
        """Initialize L1 for a new agent. Called at spawn time."""
        state = WorkingState(
            agent_id=agent_id,
            team_id=self._team_id,
            role=role,
            current_phase=TournamentPhase.BUILD,
        )
        await self._working.save(state)  # type: ignore[union-attr]
        logger.info("Initialized memory for agent %s (%s)", agent_id, role.value)

    async def teardown(self, agent_id: UUID, role: AgentRole) -> None:
        """Clear L1 for a terminated agent. L2/L3 persist."""
        await self._working.delete(role)  # type: ignore[union-attr]
        logger.info("Torn down L1 memory for agent %s (%s)", agent_id, role.value)
