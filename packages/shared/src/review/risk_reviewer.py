"""Heuristic, risk-aware review signals for diffs and design notes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(slots=True)
class RiskReviewResult:
    level: RiskLevel
    score: float  # 0.0 (safe) - 1.0 (risky)
    reasons: list[str] = field(default_factory=list)
    paths_flagged: list[str] = field(default_factory=list)


_HIGH_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(eval|exec)\s*\(", re.I), "dynamic code execution"),
    (re.compile(r"\bos\.system\s*\(", re.I), "os.system shell invocation"),
    (re.compile(r"\bsubprocess\.(run|Popen|call)\s*\(", re.I), "subprocess usage"),
    (re.compile(r"\bpickle\.loads?\s*\(", re.I), "pickle deserialization"),
    (re.compile(r"\b(yaml\.load|yaml\.unsafe_load)\s*\(", re.I), "unsafe YAML load"),
    (re.compile(r"BEGIN\s+PRIVATE\s+KEY", re.I), "private key material"),
    (re.compile(r"\b(password|secret|api_key)\s*=\s*['\"][^'\"]+['\"]", re.I), "hardcoded secret pattern"),
    (re.compile(r"\bDROP\s+TABLE\b", re.I), "destructive SQL"),
    (re.compile(r"rm\s+-rf\b", re.I), "recursive file deletion command"),
    (re.compile(r"\bchmod\s+777\b", re.I), "overly permissive chmod"),
]

_MEDIUM_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brequests\.(get|post)\s*\([^)]*verify\s*=\s*False", re.I), "TLS verify disabled"),
    (re.compile(r"\bcors\b", re.I), "CORS surface (verify policy)"),
    (re.compile(r"\bjwt\.decode\s*\([^)]*verify\s*=\s*False", re.I), "JWT verify disabled"),
    (re.compile(r"\braw_sql\b|\bexecute\s*\(\s*f[\'\"]", re.I), "possible SQL formatting"),
]

_PATH_SECRET = re.compile(r"(^|/)(\.env|id_rsa|credentials|secrets\.json)(/|$)", re.I)


def review_text_risk(
    text: str,
    *,
    paths: list[str] | None = None,
) -> RiskReviewResult:
    """
    Score arbitrary text (diff, ADR, or message) for operational/security risk.

    Deterministic heuristics only — complements (not replaces) human or LLM review.
    """
    reasons: list[str] = []
    paths_flagged: list[str] = []
    score = 0.0

    for rx, label in _HIGH_PATTERNS:
        if rx.search(text):
            reasons.append(label)
            score = max(score, 0.85)

    for rx, label in _MEDIUM_PATTERNS:
        if rx.search(text):
            reasons.append(label)
            score = max(score, 0.45)

    if paths:
        for p in paths:
            if _PATH_SECRET.search(p.replace("\\", "/")):
                paths_flagged.append(p)
                score = max(score, 0.75)

    if score >= 0.75:
        level = RiskLevel.HIGH
    elif score >= 0.35:
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.LOW

    return RiskReviewResult(
        level=level,
        score=round(score, 3),
        reasons=sorted(set(reasons)),
        paths_flagged=paths_flagged,
    )
