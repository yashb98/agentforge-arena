"""Compression helpers for long-running agent context."""

from __future__ import annotations

from packages.memory.src.compression.research_notes import (
    DEFAULT_RESEARCH_NOTES_CHAR_BUDGET,
    compress_research_notes,
)

__all__ = [
    "DEFAULT_RESEARCH_NOTES_CHAR_BUDGET",
    "compress_research_notes",
]
