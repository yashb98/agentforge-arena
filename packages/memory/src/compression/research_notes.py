"""Deterministic research note compression to fit context budgets."""

from __future__ import annotations

import re

# Default cap aligned with common "8K context slice" budgets (characters).
DEFAULT_RESEARCH_NOTES_CHAR_BUDGET = 8192

_SPLITTER = re.compile(r"\n{2,}")


def compress_research_notes(
    text: str,
    *,
    budget_chars: int = DEFAULT_RESEARCH_NOTES_CHAR_BUDGET,
) -> str:
    """
    Trim *text* to at most *budget_chars* without calling an LLM.

    Preserves the start (highest signal for titles / overview) and, when trimming,
    keeps a short tail and inserts a clear ellipsis marker.
    """
    if budget_chars < 64:
        budget_chars = 64
    stripped = text.strip()
    if len(stripped) <= budget_chars:
        return stripped

    head_room = int(budget_chars * 0.72)
    tail_room = budget_chars - head_room - 80  # budget for ellipsis lines
    if tail_room < 120:
        head_room = budget_chars - 200
        tail_room = 120

    head = stripped[:head_room].rstrip()
    tail = stripped[-tail_room:].lstrip()

    # Try paragraph-aware head shrink
    paras = _SPLITTER.split(head)
    if len(paras) > 1:
        rebuilt = paras[0]
        for p in paras[1:]:
            candidate = f"{rebuilt}\n\n{p}"
            if len(candidate) > head_room:
                break
            rebuilt = candidate
        head = rebuilt

    return (
        f"{head}\n\n"
        f"… [research notes truncated to {budget_chars} chars; "
        f"{len(stripped) - len(head) - len(tail)} chars omitted] …\n\n"
        f"{tail}"
    )
