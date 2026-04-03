"""Tests for challenge library loading helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.shared.src.challenge_library import (
    extract_challenge_title_from_markdown,
    load_validated_library_challenge,
    validate_spec_matches_markdown,
)
from packages.shared.src.types.challenge_spec import ChallengeSpecDocument

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_extract_title_strips_challenge_prefix() -> None:
    md = "# Challenge: Foo Bar\n\n## Brief\n\nx"
    assert extract_challenge_title_from_markdown(md, "fallback") == "Foo Bar"


def test_load_url_shortener_bundle() -> None:
    md, spec = load_validated_library_challenge(REPO_ROOT, "url-shortener-saas")
    assert "URL Shortener" in md
    assert isinstance(spec, ChallengeSpecDocument)
    assert spec.title == "URL Shortener SaaS"


def test_validate_spec_title_mismatch_raises() -> None:
    md, spec = load_validated_library_challenge(REPO_ROOT, "url-shortener-saas")
    bad = spec.model_copy(update={"title": "Wrong Title"})
    with pytest.raises(ValueError, match="H1 title"):
        validate_spec_matches_markdown(bad, md, "url-shortener-saas")


def test_validate_challenge_id_mismatch_raises() -> None:
    md, spec = load_validated_library_challenge(REPO_ROOT, "url-shortener-saas")
    bad = spec.model_copy(update={"challenge_id": "other"})
    with pytest.raises(ValueError, match="challenge_id"):
        validate_spec_matches_markdown(bad, md, "url-shortener-saas")
