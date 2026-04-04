"""Risk reviewer heuristics."""

from __future__ import annotations

from packages.shared.src.review.risk_reviewer import RiskLevel, review_text_risk


def test_password_file_path_flags_high() -> None:
    r = review_text_risk("no secrets", paths=["config/.env"])
    assert r.level == RiskLevel.HIGH
    assert r.paths_flagged


def test_subprocess_is_medium_or_high() -> None:
    r = review_text_risk("import subprocess\nsubprocess.run(['ls'])")
    assert r.level in (RiskLevel.MEDIUM, RiskLevel.HIGH)
