"""
Risk-aware reviewer node — deterministic signals before critic / judge phases.

Uses shared heuristics (no LLM) so orchestration can gate or annotate reviews.
"""

from __future__ import annotations

from packages.shared.src.review.risk_reviewer import RiskReviewResult, review_text_risk


def evaluate_delta_risk(
    delta_text: str,
    *,
    paths: list[str] | None = None,
) -> RiskReviewResult:
    """Score a diff or design note for operational / security risk."""
    return review_text_risk(delta_text, paths=paths)
