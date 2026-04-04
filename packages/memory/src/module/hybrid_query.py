"""Helpers for PostgreSQL full-text + optional vector retrieval."""

from __future__ import annotations

import re


def sanitize_fulltext_query(query: str, *, max_terms: int = 14) -> str | None:
    """Build a safe space-separated string for ``plainto_tsquery``."""
    tokens = [t for t in re.split(r"\W+", query.lower()) if len(t) > 1][:max_terms]
    if not tokens:
        return None
    return " ".join(tokens)
