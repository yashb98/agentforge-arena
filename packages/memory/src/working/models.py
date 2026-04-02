"""L1 Working Memory — Pydantic models for per-agent Redis state."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.shared.src.types.models import AgentRole, TournamentPhase


class WorkingState(BaseModel):
    """Per-agent working memory stored in Redis Hash + JSON."""

    model_config = ConfigDict(strict=True)

    agent_id: UUID
    team_id: UUID
    role: AgentRole
    current_phase: TournamentPhase
    current_task: str | None = None
    current_file: str | None = None
    recent_decisions: list[str] = Field(default_factory=list, description="Capped at 10")
    recent_files_touched: list[str] = Field(default_factory=list, description="Capped at 20")
    active_errors: list[str] = Field(default_factory=list, description="Uncapped")
    context_summary: str = Field(default="", description="Compressed summary from overflow handler")
    token_budget_used: int = Field(default=0, ge=0)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def cap_lists(self) -> WorkingState:
        """Enforce list caps: decisions=10, files=20."""
        if len(self.recent_decisions) > 10:
            self.recent_decisions = self.recent_decisions[-10:]
        if len(self.recent_files_touched) > 20:
            self.recent_files_touched = self.recent_files_touched[-20:]
        return self

    def estimate_tokens(self) -> int:
        """Rough token estimate (~4 chars per token)."""
        text = self.model_dump_json()
        return max(1, len(text) // 4)
