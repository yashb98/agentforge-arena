"""Simple file watcher for incremental indexing."""

from __future__ import annotations

from pathlib import Path


class CodebaseWatcher:
    """Tracks modified times and returns changed files."""

    def __init__(self) -> None:
        self._seen_mtime: dict[str, float] = {}

    def changed_files(self, files: list[str | Path]) -> list[str]:
        changed: list[str] = []
        for file_path in files:
            path = Path(file_path)
            if not path.is_file():
                continue
            mtime = path.stat().st_mtime
            key = str(path)
            previous = self._seen_mtime.get(key)
            if previous is None or mtime > previous:
                changed.append(key)
                self._seen_mtime[key] = mtime
        return changed
