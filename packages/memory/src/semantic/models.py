"""L3 Semantic Memory — Pydantic models for code search and memory context."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from packages.memory.src.module.models import ModuleRecord
from packages.memory.src.working.models import WorkingState


class CodeChunk(BaseModel):
    """A semantic chunk extracted from source code via tree-sitter."""

    model_config = ConfigDict(strict=True)

    chunk_id: str = Field(description="'{file_path}::{symbol_name}' or '{file_path}::chunk_{n}'")
    file_path: str
    language: str
    module_name: str
    symbol_name: str | None = None
    symbol_type: str | None = Field(default=None, description="function, class, method, module")
    content: str
    docstring: str | None = None
    line_start: int
    line_end: int
    dependencies: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """A single search result from L2 (module) or L3 (semantic)."""

    source: str = Field(description="'module' or 'semantic'")
    score: float = Field(ge=0.0, le=1.0)
    chunk: CodeChunk | None = None
    record: ModuleRecord | None = None
    snippet: str = Field(description="Formatted text for prompt injection")


class MemoryContext(BaseModel):
    """Combined context from all 3 memory layers. Returned by recall()."""

    working_state: WorkingState
    module_context: list[ModuleRecord]
    semantic_context: list[SearchResult]
    total_tokens_estimate: int

    def format_for_prompt(self) -> str:
        """Format all 3 layers into structured text for LLM prompt injection."""
        sections: list[str] = []

        ws = self.working_state
        l1_lines = ["## Agent Memory Context"]
        if ws.current_task:
            l1_lines.append(f"**Current Task:** {ws.current_task}")
        if ws.current_file:
            l1_lines.append(f"**Current File:** {ws.current_file}")
        if ws.context_summary:
            l1_lines.append(f"**Summary:** {ws.context_summary}")
        if ws.recent_decisions:
            l1_lines.append("**Recent Decisions:**")
            for d in ws.recent_decisions:
                l1_lines.append(f"  - {d}")
        if ws.active_errors:
            l1_lines.append("**Active Errors:**")
            for e in ws.active_errors:
                l1_lines.append(f"  - {e}")
        sections.append("\n".join(l1_lines))

        if self.module_context:
            l2_lines = ["### Relevant Knowledge"]
            for rec in self.module_context:
                l2_lines.append(f"- [{rec.record_type.value}] {rec.title}: {rec.content[:200]}")
            sections.append("\n".join(l2_lines))

        if self.semantic_context:
            l3_lines = ["### Relevant Code"]
            for sr in self.semantic_context:
                l3_lines.append(f"- {sr.snippet}")
            sections.append("\n".join(l3_lines))

        return "\n\n".join(sections)
