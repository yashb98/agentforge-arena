"""Reciprocal Rank Fusion (RRF) for merging ranked retrieval lists."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Hashable

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: list[list[Hashable]],
    *,
    k: int = DEFAULT_RRF_K,
    limit: int = 10,
) -> list[tuple[Hashable, float]]:
    """
    Merge multiple ordered result lists into a single ranking.

    ``ranked_lists`` may overlap; scores are sum_i 1/(k + rank_i) for each list
    where the item appears (1-based rank).
    """
    scores: dict[Hashable, float] = defaultdict(float)
    for lst in ranked_lists:
        for rank, item in enumerate(lst, start=1):
            scores[item] += 1.0 / (k + rank)
    ordered = sorted(scores.items(), key=lambda x: (-x[1], str(x[0])))
    return ordered[:limit]
