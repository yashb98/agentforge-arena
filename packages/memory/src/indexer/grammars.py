"""Grammar loader utilities for source language detection."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar


class GrammarLoader:
    """Lightweight language resolver used by parser/indexing pipeline."""

    _EXT_TO_LANG: ClassVar[dict[str, str]] = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".md": "markdown",
    }

    def detect_language(self, path: str | Path) -> str:
        ext = Path(path).suffix.lower()
        return self._EXT_TO_LANG.get(ext, "text")
