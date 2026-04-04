"""L2 Module Memory — Pydantic models for structured PostgreSQL records."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from packages.shared.src.types.models import AgentRole


class RecordType(StrEnum):
    """Discriminator for module memory records."""

    FILE_META = "file_meta"
    ADR = "adr"
    TECH_DEBT = "tech_debt"
    SIGNATURE = "signature"
    ACTION_LOG = "action_log"
    DEPENDENCY = "dependency"
    GOTCHA = "gotcha"
    CODING_PATTERN = "coding_pattern"
    AGENT_LEARNING = "agent_learning"
    HOOK_DISCOVERY = "hook_discovery"


class ModuleRecord(BaseModel):
    """A structured memory record stored in PostgreSQL + pgvector."""

    model_config = ConfigDict(strict=True)

    id: UUID = Field(default_factory=uuid4)
    team_id: UUID
    tournament_id: UUID
    record_type: RecordType
    module_name: str = Field(description="Logical module name, e.g., 'auth', 'api'")
    file_path: str | None = None
    title: str = Field(description="Short summary for display")
    content: str = Field(description="Full content of the record")
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )  # REASON: arbitrary JSON metadata from agents
    agent_id: UUID | None = None
    agent_role: AgentRole | None = None
    synced_to_docs: bool = Field(default=False, description="True once DocumentSyncer processed")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
