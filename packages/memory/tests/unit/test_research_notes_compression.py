"""Research notes 8K-style compression."""

from __future__ import annotations

from packages.memory.src.compression.research_notes import (
    DEFAULT_RESEARCH_NOTES_CHAR_BUDGET,
    compress_research_notes,
)


def test_compress_short_text_unchanged() -> None:
    t = "hello world"
    assert compress_research_notes(t) == "hello world"


def test_compress_long_inserts_marker_and_respects_budget() -> None:
    body = "para\n\n" * 3000
    out = compress_research_notes(body, budget_chars=DEFAULT_RESEARCH_NOTES_CHAR_BUDGET)
    assert len(out) <= DEFAULT_RESEARCH_NOTES_CHAR_BUDGET + 120
    assert "truncated" in out.lower()
