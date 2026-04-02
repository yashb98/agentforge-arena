"""Tests for DocumentSyncer (L2 records -> .md files)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from packages.memory.src.compression.doc_sync import DocumentSyncer
from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.shared.src.types.models import AgentRole


@pytest.fixture()
def workspace(tmp_path) -> Path:
    """Create a temp workspace with .claude/ structure."""
    claude_dir = tmp_path / ".claude"
    (claude_dir / "rules").mkdir(parents=True)
    (claude_dir / "agents").mkdir(parents=True)
    (claude_dir / "memory").mkdir(parents=True)
    (claude_dir / "hooks").mkdir(parents=True)
    # Create initial files
    (tmp_path / "DECISIONS.md").write_text("# Architecture Decisions\n")
    (tmp_path / "TECH_DEBT.md").write_text("# Technical Debt\n")
    (claude_dir / "rules" / "gotchas.md").write_text("# Gotchas\n")
    (claude_dir / "rules" / "project-rules.md").write_text("# Project Rules\n")
    (claude_dir / "memory" / "decisions-log.md").write_text("# Decisions Log\n")
    (claude_dir / "memory" / "gotchas.md").write_text("# Gotchas\n")
    return tmp_path


@pytest.fixture()
def syncer(workspace) -> DocumentSyncer:
    return DocumentSyncer(workspace_path=str(workspace))


class TestDocumentSyncer:
    """Tests for routing records to .md files."""

    def test_sync_adr_appends_to_decisions_md(
        self, syncer, workspace, team_id, tournament_id
    ) -> None:
        """ADR records should append to DECISIONS.md."""
        record = ModuleRecord(
            team_id=team_id,
            tournament_id=tournament_id,
            record_type=RecordType.ADR,
            module_name="auth",
            title="Chose bcrypt over argon2",
            content="bcrypt — simpler API, well-supported.",
            agent_role=AgentRole.BUILDER,
        )
        syncer.sync([record])
        content = (workspace / "DECISIONS.md").read_text()
        assert "Chose bcrypt over argon2" in content

    def test_sync_adr_also_appends_to_memory_log(
        self, syncer, workspace, team_id, tournament_id
    ) -> None:
        """ADR should also go to .claude/memory/decisions-log.md."""
        record = ModuleRecord(
            team_id=team_id,
            tournament_id=tournament_id,
            record_type=RecordType.ADR,
            module_name="auth",
            title="Chose bcrypt",
            content="bcrypt for password hashing.",
        )
        syncer.sync([record])
        content = (workspace / ".claude" / "memory" / "decisions-log.md").read_text()
        assert "Chose bcrypt" in content

    def test_sync_gotcha_to_rules_and_memory(
        self, syncer, workspace, team_id, tournament_id
    ) -> None:
        """GOTCHA should go to .claude/rules/gotchas.md AND .claude/memory/gotchas.md."""
        record = ModuleRecord(
            team_id=team_id,
            tournament_id=tournament_id,
            record_type=RecordType.GOTCHA,
            module_name="cache",
            title="Redis drops idle connections",
            content="Wrap with retry. Symptom: ConnectionError after 5min idle.",
            agent_role=AgentRole.BUILDER,
        )
        syncer.sync([record])

        rules_content = (workspace / ".claude" / "rules" / "gotchas.md").read_text()
        assert "Redis drops idle connections" in rules_content

        memory_content = (workspace / ".claude" / "memory" / "gotchas.md").read_text()
        assert "Redis drops idle connections" in memory_content

    def test_sync_coding_pattern_to_project_rules(
        self, syncer, workspace, team_id, tournament_id
    ) -> None:
        """CODING_PATTERN should go to .claude/rules/project-rules.md."""
        record = ModuleRecord(
            team_id=team_id,
            tournament_id=tournament_id,
            record_type=RecordType.CODING_PATTERN,
            module_name="api",
            title="Use Depends() for all DI",
            content="Always use FastAPI Depends() for dependency injection.",
        )
        syncer.sync([record])
        content = (workspace / ".claude" / "rules" / "project-rules.md").read_text()
        assert "Depends()" in content

    def test_sync_tech_debt_to_tech_debt_md(
        self, syncer, workspace, team_id, tournament_id
    ) -> None:
        """TECH_DEBT should append to TECH_DEBT.md."""
        record = ModuleRecord(
            team_id=team_id,
            tournament_id=tournament_id,
            record_type=RecordType.TECH_DEBT,
            module_name="orm",
            title="UUID workaround in ORM",
            content="SQLAlchemy UUID handling has a bug, using string cast.",
        )
        syncer.sync([record])
        content = (workspace / "TECH_DEBT.md").read_text()
        assert "UUID workaround" in content

    def test_sync_skips_duplicate_titles(
        self, syncer, workspace, team_id, tournament_id
    ) -> None:
        """Should not append if the exact title already exists in the file."""
        record = ModuleRecord(
            team_id=team_id,
            tournament_id=tournament_id,
            record_type=RecordType.ADR,
            module_name="auth",
            title="Chose bcrypt",
            content="bcrypt for hashing.",
        )
        syncer.sync([record])
        syncer.sync([record])  # Second time
        content = (workspace / "DECISIONS.md").read_text()
        assert content.count("Chose bcrypt") == 1

    def test_sync_returns_synced_record_ids(
        self, syncer, workspace, team_id, tournament_id
    ) -> None:
        """sync() should return the IDs of records it processed."""
        record = ModuleRecord(
            team_id=team_id,
            tournament_id=tournament_id,
            record_type=RecordType.ADR,
            module_name="auth",
            title="Some ADR",
            content="Content.",
        )
        ids = syncer.sync([record])
        assert record.id in ids
