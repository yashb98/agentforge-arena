"""
Challenge library machine spec (v1) — ``challenge.spec.json``.

Validated with Pydantic ``extra='forbid'``. See docs/superpowers/specs/2026-04-03-challenge-spec-v1-design.md.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.shared.src.types.models import (
    AgentRole,
    ChallengeCategory,
    ChallengeDifficulty,
    TournamentFormat,
    TournamentPhase,
)


class ChallengeMetadataSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: ChallengeCategory
    difficulty: ChallengeDifficulty
    tags: list[str] = Field(default_factory=list)
    time_limit_minutes: int = Field(default=90, ge=1, le=24 * 60)


class PhaseHintBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objectives: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)


class MilestoneSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    phase: TournamentPhase
    label: str = Field(min_length=1)
    completion_criteria_ref: str = Field(
        default="",
        description="Reference into requirements or an external doc (v1 opaque string).",
    )


class OrchestrationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tournament_formats_allowed: list[TournamentFormat] = Field(min_length=1)
    phase_hints: dict[str, PhaseHintBlock] = Field(default_factory=dict)
    milestones: list[MilestoneSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def phase_hint_keys_are_phases(self) -> OrchestrationSpec:
        valid = {p.value for p in TournamentPhase} - {"cancelled"}
        for key in self.phase_hints:
            if key not in valid:
                msg = f"orchestration.phase_hints key {key!r} must be a TournamentPhase value"
                raise ValueError(msg)
        return self


class DeliverySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_readme_required: bool = True
    artifact_globs: list[str] = Field(default_factory=list)


class QualityCommandSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    cmd: list[str] = Field(min_length=1, description="Argv tokens (no shell).")
    required: bool = True


class QualitySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commands: list[QualityCommandSpec] = Field(default_factory=list)


class JudgeCriterionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, description="Stable id; matches judge dimension keys where applicable.")
    weight: float = Field(ge=0.0, le=1.0)
    description: str = Field(default="")


class JudgePassGateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(min_length=1)
    min_score: float = Field(ge=0.0, le=1.0, description="Normalized gate vs criterion (0-1 scale).")


class JudgeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric_version: str = Field(min_length=1)
    criteria: list[JudgeCriterionSpec] = Field(min_length=1)
    pass_gates: list[JudgePassGateSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def pass_gates_reference_criteria(self) -> JudgeSpec:
        ids = {c.id for c in self.criteria}
        for gate in self.pass_gates:
            if gate.criterion_id not in ids:
                msg = f"pass_gates criterion_id {gate.criterion_id!r} not found in criteria"
                raise ValueError(msg)
        return self


class AgentRoleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus: list[str] = Field(default_factory=list)


class AgentsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_constraints: list[str] = Field(default_factory=list)
    roles: dict[str, AgentRoleSpec] = Field(default_factory=dict)

    @model_validator(mode="after")
    def role_keys_are_known(self) -> AgentsSpec:
        allowed = {r.value for r in AgentRole}
        for key in self.roles:
            if key not in allowed:
                msg = f"agents.roles key {key!r} must be an AgentRole value"
                raise ValueError(msg)
        return self


class ChallengeSpecDocument(BaseModel):
    """Root object stored in ``challenge.spec.json``."""

    model_config = ConfigDict(extra="forbid")

    spec_version: str = Field(min_length=1, description="Format version of this JSON document.")
    challenge_id: str = Field(min_length=1, description="Must match library directory name.")
    title: str = Field(min_length=1)
    metadata: ChallengeMetadataSpec
    requirements: list[str] = Field(min_length=1)
    orchestration: OrchestrationSpec
    delivery: DeliverySpec
    quality: QualitySpec
    judge: JudgeSpec
    agents: AgentsSpec
    hidden_test_hints: list[str] = Field(default_factory=list)
