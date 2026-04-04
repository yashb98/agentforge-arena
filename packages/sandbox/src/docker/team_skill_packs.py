"""Seed `project/.claude/skills/` from bundled pack directories."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Adjacent to this file: resources/team_skills/<pack-name>/...
_BUNDLE_ROOT = Path(__file__).resolve().parent / "resources" / "team_skills"


def seed_team_skill_packs(project_root: Path) -> list[str]:
    """Copy each subdirectory of the bundle into ``project_root/.claude/skills/``.

    Skips non-directories, README.md at bundle root, and names starting with
    ``_`` or ``.``.

    Returns the list of pack directory names copied.
    """
    dest_base = project_root / ".claude" / "skills"
    dest_base.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    if not _BUNDLE_ROOT.is_dir():
        logger.debug("No bundled team skills at %s", _BUNDLE_ROOT)
        return copied

    for child in sorted(_BUNDLE_ROOT.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith((".", "_")):
            continue
        target = dest_base / child.name
        try:
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(child, target)
        except OSError:
            logger.exception("Failed to copy skill pack %s", child.name)
            continue
        copied.append(child.name)

    if copied:
        logger.info("Seeded team skill packs: %s", ", ".join(copied))
    return copied
