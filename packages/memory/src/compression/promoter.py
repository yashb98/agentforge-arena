"""Memory Promoter — Deterministic L1 -> L2 keyword-based promotion."""

from __future__ import annotations

import re
from collections import Counter
from uuid import UUID

from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.working.models import WorkingState

# Keyword patterns per record type (case-insensitive)
PROMOTION_RULES: list[tuple[RecordType, re.Pattern[str]]] = [
    (
        RecordType.ADR,
        re.compile(r"\b(chose|decided|architecture|design|picked|selected)\b", re.IGNORECASE),
    ),
    (
        RecordType.TECH_DEBT,
        re.compile(r"\b(bug|fix|workaround|hack|TODO|FIXME|shortcut)\b", re.IGNORECASE),
    ),
    (
        RecordType.GOTCHA,
        re.compile(
            r"\b(gotcha|careful|don'?t|never|always|footgun|breaks|beware)\b", re.IGNORECASE
        ),
    ),
    (
        RecordType.CODING_PATTERN,
        re.compile(r"\b(pattern|convention|must use|should use|prefer|standard)\b", re.IGNORECASE),
    ),
    (
        RecordType.AGENT_LEARNING,
        re.compile(
            r"\b(learned|discovered|realized|turns out|insight|found that)\b", re.IGNORECASE
        ),
    ),
    (
        RecordType.HOOK_DISCOVERY,
        re.compile(
            r"\b(formatter|linter|hook|auto-format|pre-commit|ruff|eslint)\b", re.IGNORECASE
        ),
    ),
]

# Files touched more than this many times get promoted as FILE_META
FILE_FREQUENCY_THRESHOLD = 3


class MemoryPromoter:
    """Promotes important L1 items to L2 records using deterministic keyword matching.

    No LLM calls. Pure Python logic.
    """

    def promote(
        self,
        state: WorkingState,
        *,
        tournament_id: UUID,
    ) -> list[ModuleRecord]:
        """Scan working state and create L2 records for promotable items."""
        records: list[ModuleRecord] = []

        # Promote decisions by keyword
        for decision in state.recent_decisions:
            record_type = self._classify_decision(decision)
            if record_type is not None:
                records.append(
                    ModuleRecord(
                        team_id=state.team_id,
                        tournament_id=tournament_id,
                        record_type=record_type,
                        module_name=self._infer_module(state),
                        title=decision[:200],
                        content=decision,
                        agent_id=state.agent_id,
                        agent_role=state.role,
                    ),
                )

        # Promote frequently-touched files
        file_counts = Counter(state.recent_files_touched)
        for file_path, count in file_counts.items():
            if count > FILE_FREQUENCY_THRESHOLD:
                records.append(
                    ModuleRecord(
                        team_id=state.team_id,
                        tournament_id=tournament_id,
                        record_type=RecordType.FILE_META,
                        module_name=self._module_from_path(file_path),
                        file_path=file_path,
                        title=f"Frequently modified: {file_path}",
                        content=f"Modified {count} times during this sprint.",
                        agent_id=state.agent_id,
                        agent_role=state.role,
                    ),
                )

        return records

    def _classify_decision(self, text: str) -> RecordType | None:
        """Classify a decision string into a RecordType using keyword matching."""
        for record_type, pattern in PROMOTION_RULES:
            if pattern.search(text):
                return record_type
        return None

    def _infer_module(self, state: WorkingState) -> str:
        """Infer module name from current file or task."""
        if state.current_file:
            return self._module_from_path(state.current_file)
        if state.current_task:
            return "general"
        return "unknown"

    def _module_from_path(self, path: str) -> str:
        """Extract module name from a file path."""
        parts = path.replace("\\", "/").split("/")
        for i, part in enumerate(parts):
            if part == "src" and i + 1 < len(parts):
                return parts[i + 1].replace(".py", "").replace(".ts", "")
        if len(parts) >= 2:
            return parts[-2]
        return parts[0] if parts else "unknown"
