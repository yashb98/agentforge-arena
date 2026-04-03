"""Memory manager entrypoint for agent recall and record operations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from packages.shared.src.types.models import AgentRole

logger = logging.getLogger(__name__)


class WorkingStoreProtocol(Protocol):
    """Minimal behavior required from the L1 working-memory store."""

    async def get_state(self, agent_id: UUID) -> dict[str, Any]:
        ...

    async def upsert_state(self, agent_id: UUID, patch: dict[str, Any]) -> dict[str, Any]:
        ...

    async def append_event(self, agent_id: UUID, event: dict[str, Any]) -> dict[str, Any]:
        ...


class MemoryManager:
    """Coordinates memory read/write paths used by agent runtime loops."""

    def __init__(self, working_store: WorkingStoreProtocol) -> None:
        self._working_store = working_store

    async def recall(
        self,
        agent_id: UUID,
        role: AgentRole,
        query: str,
    ) -> dict[str, Any]:
        """
        Build context payload for an agent turn.

        This PR1 implementation uses only L1 working memory while keeping
        the return envelope stable for later L2/L3 additions.
        """
        try:
            l1 = await self._working_store.get_state(agent_id)
        except Exception:
            logger.exception("L1 recall failed for agent %s", agent_id)
            l1 = {}
        return {
            "agent_id": str(agent_id),
            "role": role.value,
            "query": query,
            "l1": l1,
            "l2": [],
            "l3": [],
        }

    async def record(
        self,
        agent_id: UUID,
        role: AgentRole,
        *,
        task: str | None = None,
        decision: str | None = None,
        notes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist latest task/decision signals without breaking agent flow."""
        patch: dict[str, Any] = {
            "role": role.value,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if task is not None:
            patch["last_task"] = task
        if decision is not None:
            patch["last_decision"] = decision
        if notes is not None:
            patch["notes"] = notes
        if metadata is not None:
            patch["metadata"] = metadata

        try:
            await self._working_store.upsert_state(agent_id, patch)
            await self._working_store.append_event(
                agent_id,
                {
                    "event": "record",
                    "task": task,
                    "decision": decision,
                },
            )
        except Exception:
            # Memory must never crash the agent runtime loop.
            logger.exception("Memory record failed for agent %s", agent_id)
