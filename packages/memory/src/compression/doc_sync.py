"""Document Syncer — Route L2 records to project .md files."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from packages.memory.src.module.models import ModuleRecord, RecordType

logger = logging.getLogger(__name__)

# Routing table: RecordType -> list of relative file paths
ROUTING_TABLE: dict[RecordType, list[str]] = {
    RecordType.ADR: ["DECISIONS.md", ".claude/memory/decisions-log.md"],
    RecordType.TECH_DEBT: ["TECH_DEBT.md", ".claude/rules/gotchas.md", ".claude/memory/gotchas.md"],
    RecordType.GOTCHA: [".claude/rules/gotchas.md", ".claude/memory/gotchas.md"],
    RecordType.CODING_PATTERN: [".claude/rules/project-rules.md", ".claude/rules/stack-rules.md"],
    RecordType.AGENT_LEARNING: [".claude/agents/{role}-notes.md"],
    RecordType.HOOK_DISCOVERY: [".claude/hooks/{title}.sh"],
    RecordType.FILE_META: [],
    RecordType.DEPENDENCY: [],
    RecordType.ACTION_LOG: [],
    RecordType.SIGNATURE: [],
}


class DocumentSyncer:
    """Routes L2 ModuleRecords to the appropriate project .md files.

    Deterministic appends for most types. Deduplicates by title.
    """

    def __init__(self, workspace_path: str) -> None:
        self._workspace = Path(workspace_path)

    def sync(self, records: list[ModuleRecord]) -> list[UUID]:
        """Sync a batch of records to their target .md files.

        Returns list of record IDs that were successfully synced.
        """
        synced_ids: list[UUID] = []

        for record in records:
            targets = ROUTING_TABLE.get(record.record_type, [])
            if not targets:
                continue

            for target_template in targets:
                target_path = self._resolve_path(target_template, record)
                if target_path is None:
                    continue

                # Ensure parent directory exists
                target_path.parent.mkdir(parents=True, exist_ok=True)

                # Read existing content for dedup
                existing = ""
                if target_path.exists():
                    existing = target_path.read_text()

                # Skip if title already present (dedup)
                if record.title in existing:
                    logger.debug("Skipping duplicate: %s in %s", record.title, target_path)
                    continue

                # Format and append
                entry = self._format_entry(record)
                with target_path.open("a") as f:
                    f.write(entry)

                logger.debug(
                    "Synced %s record '%s' to %s",
                    record.record_type.value,
                    record.title,
                    target_path,
                )

            synced_ids.append(record.id)

        return synced_ids

    def _resolve_path(self, template: str, record: ModuleRecord) -> Path | None:
        """Resolve a path template with record data."""
        try:
            resolved = template.format(
                role=record.agent_role.value if record.agent_role else "unknown",
                title=record.title.lower().replace(" ", "-")[:50],
            )
        except (KeyError, AttributeError):
            resolved = template
        return self._workspace / resolved

    def _format_entry(self, record: ModuleRecord) -> str:
        """Format a record as a markdown entry."""
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        agent_info = f" | **Agent:** {record.agent_role.value}" if record.agent_role else ""

        if record.record_type == RecordType.ADR:
            return (
                f"\n## ADR: {record.title}\n"
                f"**Date:** {now}{agent_info}\n"
                f"**Module:** {record.module_name}\n"
                f"{record.content}\n"
            )

        if record.record_type == RecordType.GOTCHA:
            return f"\n## G: {record.title}\n**Discovered:** {now}{agent_info}\n{record.content}\n"

        if record.record_type == RecordType.TECH_DEBT:
            return (
                f"\n## DEBT: {record.title}\n"
                f"**Date:** {now}{agent_info}\n"
                f"**Module:** {record.module_name}\n"
                f"{record.content}\n"
            )

        if record.record_type == RecordType.CODING_PATTERN:
            return (
                f"\n## Pattern: {record.title}\n"
                f"**Module:** {record.module_name}\n"
                f"{record.content}\n"
            )

        if record.record_type == RecordType.AGENT_LEARNING:
            return f"\n## Learning: {record.title}\n**Date:** {now}\n{record.content}\n"

        # Default format
        return f"\n## {record.title}\n{record.content}\n"
