"""Tests for risk-aware review node."""

from __future__ import annotations

from packages.agents.src.review.risk_aware_node import evaluate_delta_risk
from packages.shared.src.review.risk_reviewer import RiskLevel


def test_evaluate_delta_high_on_exec() -> None:
    r = evaluate_delta_risk("fix = eval(user_input)")
    assert r.level == RiskLevel.HIGH
    assert r.score >= 0.75
    assert r.reasons


def test_evaluate_delta_low_on_benign() -> None:
    r = evaluate_delta_risk("def add(a, b):\n    return a + b\n")
    assert r.level == RiskLevel.LOW
    assert r.score < 0.35
