"""Tests for bundled team skill pack seeding."""

from __future__ import annotations

from packages.sandbox.src.docker.team_skill_packs import seed_team_skill_packs
from packages.sandbox.src.docker.team_workspace_seed import write_team_code_review_graph_seed


def test_seed_team_skill_packs_copies_bundled_packs(tmp_path) -> None:
    project = tmp_path / "project"
    (project / ".claude" / "skills").mkdir(parents=True)

    copied = seed_team_skill_packs(project)

    assert "arena-project-hints" in copied
    assert "build-graph" in copied
    assert "review-delta" in copied
    assert "review-pr" in copied
    assert "hermes-test-driven-development" in copied
    skill_md = project / ".claude" / "skills" / "arena-project-hints" / "SKILL.md"
    assert skill_md.is_file()
    text = skill_md.read_text(encoding="utf-8")
    assert "arena-project-hints" in text
    assert "challenge.spec.json" in text
    hermes_md = project / ".claude" / "skills" / "hermes-test-driven-development" / "SKILL.md"
    assert hermes_md.is_file()
    assert "Test-Driven Development" in hermes_md.read_text(encoding="utf-8")


def test_write_team_code_review_graph_seed_writes_mcp_and_ignore(tmp_path) -> None:
    project = tmp_path / "project"
    write_team_code_review_graph_seed(project)
    mcp = project / ".mcp.json"
    assert mcp.is_file()
    assert "code-review-graph" in mcp.read_text(encoding="utf-8")
    ign = project / ".code-review-graphignore"
    assert ign.is_file()
    assert "node_modules/" in ign.read_text(encoding="utf-8")
