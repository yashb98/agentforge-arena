"""Context Compressor — Haiku 4.5 summarization for L1 overflow."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from packages.memory.src.working.models import WorkingState

logger = logging.getLogger(__name__)

COMPRESSION_MODEL = "claude-haiku-4-5"

COMPRESSION_PROMPT = """Summarize this agent's working state into a dense paragraph.
Preserve: current task, key decisions, unresolved errors, files modified.
Drop: routine actions, redundant info, resolved issues.

Working state:
{state_text}

Write a concise summary (max 500 tokens):"""


@dataclass
class CompressedContext:
    """Result of compressing an agent's working state."""

    summary: str
    preserved_decisions: list[str]
    dropped_count: int


class ContextCompressor:
    """Calls Haiku 4.5 to compress L1 working state when it exceeds token threshold.

    Cost: ~$0.001 per compression. Latency: ~500ms.
    """

    def __init__(self, llm_client: Any) -> None:
        self._llm = llm_client

    async def compress(self, state: WorkingState) -> CompressedContext:
        """Compress a working state into a summary + preserved top decisions."""
        state_text = state.model_dump_json(indent=2)

        response = await self._llm.completion(
            messages=[
                {"role": "user", "content": COMPRESSION_PROMPT.format(state_text=state_text)},
            ],
            model=COMPRESSION_MODEL,
            temperature=0.1,
            max_tokens=600,
            trace_name="memory.compress",
            trace_metadata={
                "agent_id": str(state.agent_id),
                "role": state.role.value,
            },
        )

        # Preserve the 3 most recent decisions verbatim
        preserved = state.recent_decisions[-3:] if state.recent_decisions else []
        dropped = max(0, len(state.recent_decisions) - 3)

        return CompressedContext(
            summary=response.content,
            preserved_decisions=preserved,
            dropped_count=dropped,
        )

    def apply(self, state: WorkingState, compressed: CompressedContext) -> WorkingState:
        """Apply compression results to working state."""
        return state.model_copy(
            update={
                "context_summary": compressed.summary,
                "recent_decisions": compressed.preserved_decisions,
                "recent_files_touched": state.recent_files_touched[-10:],
            }
        )
