"""
Load and validate challenges from ``challenges/library/<id>/``.

Human narrative: ``CHALLENGE.md``. Machine contract: ``challenge.spec.json``.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path  # noqa: TC003

from pydantic import ValidationError

from packages.shared.src.types.challenge_spec import ChallengeSpecDocument

logger = logging.getLogger(__name__)


def extract_challenge_title_from_markdown(content: str, fallback_id: str) -> str:
    """First H1 line, stripping optional ``Challenge:`` prefix (matches API parser)."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            raw_title = stripped[2:].strip()
            return re.sub(r"^Challenge:\s*", "", raw_title, flags=re.IGNORECASE)
    return fallback_id


def parse_challenge_spec_json(raw: str | bytes) -> ChallengeSpecDocument:
    """Parse JSON into a strict ``ChallengeSpecDocument``."""
    data = json.loads(raw.decode("utf-8")) if isinstance(raw, bytes) else json.loads(raw)
    return ChallengeSpecDocument.model_validate(data)


def validate_spec_matches_markdown(
    spec: ChallengeSpecDocument,
    markdown: str,
    directory_name: str,
) -> None:
    """Ensure spec ids match folder and H1 title matches ``spec.title``."""
    if spec.challenge_id != directory_name:
        msg = f"spec.challenge_id {spec.challenge_id!r} != directory {directory_name!r}"
        raise ValueError(msg)
    md_title = extract_challenge_title_from_markdown(markdown, directory_name)
    if md_title.strip() != spec.title.strip():
        msg = f"CHALLENGE.md H1 title {md_title!r} != spec.title {spec.title!r}"
        raise ValueError(msg)


def load_challenge_spec_file(path: Path) -> ChallengeSpecDocument:
    """Read and validate ``challenge.spec.json`` at ``path``."""
    raw = path.read_text(encoding="utf-8")
    return parse_challenge_spec_json(raw)


def library_paths(repo_root: Path, challenge_id: str) -> tuple[Path, Path]:
    """Return ``(CHALLENGE.md path, challenge.spec.json path)``."""
    base = repo_root / "challenges" / "library" / challenge_id
    return base / "CHALLENGE.md", base / "challenge.spec.json"


def load_validated_library_challenge(
    repo_root: Path,
    challenge_id: str,
) -> tuple[str, ChallengeSpecDocument]:
    """
    Load markdown + spec; validate spec and sync with markdown.

    Raises:
        FileNotFoundError: Missing ``CHALLENGE.md`` or ``challenge.spec.json``.
        ValidationError: Invalid spec JSON.
        ValueError: Spec/markdown/folder mismatch.
    """
    md_path, spec_path = library_paths(repo_root, challenge_id)
    if not md_path.is_file():
        raise FileNotFoundError(str(md_path))
    if not spec_path.is_file():
        raise FileNotFoundError(str(spec_path))
    markdown = md_path.read_text(encoding="utf-8")
    try:
        spec = load_challenge_spec_file(spec_path)
    except ValidationError:
        logger.exception("Invalid challenge.spec.json for %s", challenge_id)
        raise
    validate_spec_matches_markdown(spec, markdown, challenge_id)
    return markdown, spec


def iter_library_challenge_ids(repo_root: Path) -> list[str]:
    """Subdirectory names under ``challenges/library`` that contain ``CHALLENGE.md``."""
    library = repo_root / "challenges" / "library"
    if not library.is_dir():
        return []
    return sorted(
        d.name
        for d in library.iterdir()
        if d.is_dir() and (d / "CHALLENGE.md").is_file()
    )
