"""
AgentForge Arena — Challenge Routes

Endpoints for browsing the challenge library. Challenges are loaded from
the filesystem at ``challenges/library/<id>/CHALLENGE.md``. Results are
cached in memory after first load to avoid repeated disk I/O.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from packages.shared.src.types.models import ChallengeCategory, ChallengeDifficulty
from packages.shared.src.types.responses import ChallengeListResponse, ChallengeResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["challenges"])

# Module-level cache — populated on first request, never invalidated at runtime.
# Maps challenge_id (str) → ChallengeResponse.
_challenge_cache: dict[str, ChallengeResponse] | None = None

# Root of the repository: packages/api/src/routes → parents[4] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]
_LIBRARY_DIR = _REPO_ROOT / "challenges" / "library"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_DIFFICULTY_MAP: dict[str, ChallengeDifficulty] = {
    "easy": ChallengeDifficulty.EASY,
    "medium": ChallengeDifficulty.MEDIUM,
    "hard": ChallengeDifficulty.HARD,
    "expert": ChallengeDifficulty.EXPERT,
}

_CATEGORY_MAP: dict[str, ChallengeCategory] = {
    "saas app": ChallengeCategory.SAAS_APP,
    "saas_app": ChallengeCategory.SAAS_APP,
    "cli tool": ChallengeCategory.CLI_TOOL,
    "cli_tool": ChallengeCategory.CLI_TOOL,
    "ai agent": ChallengeCategory.AI_AGENT,
    "ai_agent": ChallengeCategory.AI_AGENT,
    "api service": ChallengeCategory.API_SERVICE,
    "api_service": ChallengeCategory.API_SERVICE,
    "real time": ChallengeCategory.REAL_TIME,
    "real_time": ChallengeCategory.REAL_TIME,
    "data pipeline": ChallengeCategory.DATA_PIPELINE,
    "data_pipeline": ChallengeCategory.DATA_PIPELINE,
}


def _parse_challenge_md(challenge_id: str, content: str) -> ChallengeResponse:
    """Parse a CHALLENGE.md file and return a ChallengeResponse.

    Parsing rules (tolerant — missing fields get defaults):
    - Title: first H1 heading after ``Challenge:`` prefix
    - Difficulty / Category / Time: from the ``## Difficulty:`` meta line
    - Description: the ``## Brief`` section body
    - Requirements: numbered list items under ``## Requirements``
    - Tags: derived from category + difficulty values
    """
    lines = content.splitlines()

    # --- Title ---
    title = challenge_id  # default
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            raw_title = stripped[2:].strip()
            # Strip "Challenge: " prefix if present
            title = re.sub(r"^Challenge:\s*", "", raw_title, flags=re.IGNORECASE)
            break

    # --- Meta line: ## Difficulty: Medium | Category: SaaS App | Time: 90 minutes ---
    difficulty = ChallengeDifficulty.MEDIUM
    category = ChallengeCategory.SAAS_APP
    time_limit_minutes = 90

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## Difficulty:") or stripped.startswith("## Difficulty "):
            meta = stripped.split("##", 1)[1].strip()  # "Difficulty: Medium | Category: ..."
            parts = [p.strip() for p in meta.split("|")]
            for part in parts:
                if ":" not in part:
                    continue
                key, _, value = part.partition(":")
                key = key.strip().lower()
                value = value.strip()
                if key == "difficulty":
                    difficulty = _DIFFICULTY_MAP.get(value.lower(), ChallengeDifficulty.MEDIUM)
                elif key == "category":
                    category = _CATEGORY_MAP.get(value.lower(), ChallengeCategory.SAAS_APP)
                elif key == "time":
                    # "90 minutes" → 90
                    m = re.search(r"\d+", value)
                    if m:
                        time_limit_minutes = int(m.group())
            break

    # --- Description: ## Brief section ---
    description_lines: list[str] = []
    in_brief = False
    for line in lines:
        if line.strip().lower().startswith("## brief"):
            in_brief = True
            continue
        if in_brief:
            if line.startswith("## "):
                break
            description_lines.append(line)
    description = "\n".join(description_lines).strip()
    if not description:
        description = title  # fallback

    # --- Requirements: numbered list items under ## Requirements ---
    requirements: list[str] = []
    in_req = False
    for line in lines:
        if line.strip().lower().startswith("## requirements"):
            in_req = True
            continue
        if in_req:
            if line.startswith("## "):
                break
            # Match numbered list items: "1. **Create Short URL** — …"
            m = re.match(r"^\s*\d+\.\s+(.*)", line)
            if m:
                # Strip bold markers and em-dash formatting
                req_text = re.sub(r"\*\*(.+?)\*\*", r"\1", m.group(1)).strip()
                requirements.append(req_text)

    if not requirements:
        requirements = ["See CHALLENGE.md for requirements"]

    # --- Tags: derived from category + difficulty ---
    tags = [category.value, difficulty.value]

    return ChallengeResponse(
        id=challenge_id,
        title=title,
        description=description,
        category=category,
        difficulty=difficulty,
        time_limit_minutes=time_limit_minutes,
        requirements=requirements,
        tags=tags,
    )


def _load_challenges() -> dict[str, ChallengeResponse]:
    """Load all challenges from disk and return them keyed by challenge ID.

    Each subdirectory of ``challenges/library/`` is treated as a challenge.
    The directory name becomes the challenge ID. The ``CHALLENGE.md`` inside
    is parsed for metadata.
    """
    challenges: dict[str, ChallengeResponse] = {}

    if not _LIBRARY_DIR.is_dir():
        logger.warning("Challenge library directory not found: %s", _LIBRARY_DIR)
        return challenges

    for challenge_dir in sorted(_LIBRARY_DIR.iterdir()):
        if not challenge_dir.is_dir():
            continue

        challenge_id = challenge_dir.name
        challenge_file = challenge_dir / "CHALLENGE.md"

        if not challenge_file.is_file():
            logger.warning("No CHALLENGE.md in %s — skipping", challenge_dir)
            continue

        try:
            content = challenge_file.read_text(encoding="utf-8")
            challenges[challenge_id] = _parse_challenge_md(challenge_id, content)
        except Exception:
            logger.exception("Failed to parse challenge %s", challenge_id)

    logger.info("Loaded %d challenge(s) from library", len(challenges))
    return challenges


def _get_challenge_cache() -> dict[str, ChallengeResponse]:
    """Return the in-memory challenge cache, loading from disk on first call."""
    global _challenge_cache
    if _challenge_cache is None:
        _challenge_cache = _load_challenges()
    return _challenge_cache


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/challenges",
    response_model=ChallengeListResponse,
    summary="List available challenges",
    description=(
        "Returns all challenges from the challenge library. "
        "Results are loaded from the filesystem on first request and cached in memory."
    ),
)
async def list_challenges() -> ChallengeListResponse:
    """Return all available hackathon challenges."""
    cache = _get_challenge_cache()
    challenges = list(cache.values())
    return ChallengeListResponse(challenges=challenges, total=len(challenges))


@router.get(
    "/challenges/{challenge_id}",
    response_model=ChallengeResponse,
    summary="Get a specific challenge",
    description=(
        "Returns the full details for a challenge by its ID "
        "(the directory name under ``challenges/library/``). "
        "Returns 404 if the challenge does not exist."
    ),
)
async def get_challenge(challenge_id: str) -> ChallengeResponse:
    """Return a single challenge by ID, or 404 if not found."""
    cache = _get_challenge_cache()
    challenge = cache.get(challenge_id)
    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Challenge '{challenge_id}' not found",
        )
    return challenge
