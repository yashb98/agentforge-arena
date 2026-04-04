"""Reciprocal rank fusion."""

from __future__ import annotations

from uuid import uuid4

from packages.memory.src.module.rrf import reciprocal_rank_fusion


def test_rrf_merges_overlap() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    ranked = reciprocal_rank_fusion(
        [[a, b], [b, c]],
        k=60,
        limit=10,
    )
    ids = [r[0] for r in ranked]
    assert b in ids
    assert ids[0] == b
