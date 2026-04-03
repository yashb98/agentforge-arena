"""Tests for ``challenge.spec.json`` Pydantic models."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.shared.src.types.challenge_spec import ChallengeSpecDocument
from packages.shared.src.types.models import TournamentFormat, TournamentPhase

REPO_ROOT = Path(__file__).resolve().parents[3]


def _minimal_spec_dict() -> dict:
    return {
        "spec_version": "1.0",
        "challenge_id": "x",
        "title": "X",
        "metadata": {
            "category": "saas_app",
            "difficulty": "medium",
            "tags": [],
            "time_limit_minutes": 90,
        },
        "requirements": ["Do the thing"],
        "orchestration": {
            "tournament_formats_allowed": ["duel"],
            "phase_hints": {},
            "milestones": [],
        },
        "delivery": {"root_readme_required": True, "artifact_globs": []},
        "quality": {"commands": []},
        "judge": {
            "rubric_version": "1",
            "criteria": [{"id": "functionality", "weight": 1.0, "description": "x"}],
            "pass_gates": [],
        },
        "agents": {"global_constraints": [], "roles": {}},
        "hidden_test_hints": [],
    }


def test_minimal_spec_validates() -> None:
    doc = ChallengeSpecDocument.model_validate(_minimal_spec_dict())
    assert doc.challenge_id == "x"


def test_extra_top_level_field_rejected() -> None:
    d = _minimal_spec_dict()
    d["unknown"] = 1
    with pytest.raises(ValidationError):
        ChallengeSpecDocument.model_validate(d)


def test_pass_gate_must_reference_criterion() -> None:
    d = _minimal_spec_dict()
    d["judge"]["pass_gates"] = [{"criterion_id": "nope", "min_score": 0.5}]
    with pytest.raises(ValidationError, match="pass_gates"):
        ChallengeSpecDocument.model_validate(d)


def test_phase_hints_key_must_be_phase() -> None:
    d = _minimal_spec_dict()
    d["orchestration"]["phase_hints"] = {
        "not_a_phase": {"objectives": []},
    }
    with pytest.raises(ValidationError, match="phase_hints"):
        ChallengeSpecDocument.model_validate(d)


def test_agents_role_key_must_be_valid() -> None:
    d = _minimal_spec_dict()
    d["agents"]["roles"] = {"not_a_role": {"focus": []}}
    with pytest.raises(ValidationError, match="roles"):
        ChallengeSpecDocument.model_validate(d)


@pytest.mark.parametrize(
    "slug",
    ["url-shortener-saas", "task-queue-engine", "realtime-chat-app"],
)
def test_library_challenge_spec_files_validate(slug: str) -> None:
    path = REPO_ROOT / "challenges" / "library" / slug / "challenge.spec.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    doc = ChallengeSpecDocument.model_validate(raw)
    assert doc.challenge_id == slug
    assert doc.orchestration.tournament_formats_allowed
    assert TournamentFormat.DUEL in doc.orchestration.tournament_formats_allowed


def test_milestone_phase_enum() -> None:
    d = _minimal_spec_dict()
    d["orchestration"]["milestones"] = [
        {
            "id": "m1",
            "phase": "research",
            "label": "Research done",
            "completion_criteria_ref": "req-1",
        }
    ]
    doc = ChallengeSpecDocument.model_validate(d)
    assert doc.orchestration.milestones[0].phase == TournamentPhase.RESEARCH
