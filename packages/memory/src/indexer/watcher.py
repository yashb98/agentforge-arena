"""Codebase Watcher — Debounced 60s mtime-based file change detection."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 60
SUPPORTED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".md"}


class CodebaseWatcher:
    """Scans workspace for changed files every 60 seconds and triggers indexing.

    Uses mtime-based change detection. No filesystem watchers needed.
    Runs as an asyncio.Task per team.
    """

    def __init__(
        self,
        workspace_path: str,
        pipeline: object,
        debounce_seconds: int = DEBOUNCE_SECONDS,
    ) -> None:
        self._workspace = Path(workspace_path)
        self._pipeline = pipeline
        self._debounce = debounce_seconds
        self._last_mtimes: dict[str, float] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the watcher loop as a background task."""
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("CodebaseWatcher started for %s", self._workspace)

    async def stop(self) -> None:
        """Stop the watcher loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("CodebaseWatcher stopped for %s", self._workspace)

    async def _watch_loop(self) -> None:
        """Main loop: scan, detect changes, trigger indexing."""
        while self._running:
            try:
                changed, removed = self._scan_changes()
                if changed:
                    await self._pipeline.index_files(changed)  # type: ignore[union-attr]
                if removed:
                    await self._pipeline.remove_files(removed)  # type: ignore[union-attr]
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Watcher error")

            await asyncio.sleep(self._debounce)

    def _scan_changes(self) -> tuple[list[str], list[str]]:
        """Scan workspace for changed and removed files."""
        changed: list[str] = []
        current_files: set[str] = set()

        for root, _dirs, files in os.walk(self._workspace):
            root_path = Path(root)
            if any(p.startswith(".") for p in root_path.parts):
                continue
            if any(p in ("node_modules", "__pycache__", ".git", "venv") for p in root_path.parts):
                continue

            for fname in files:
                fpath = os.path.join(root, fname)
                ext = os.path.splitext(fname)[1]
                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                current_files.add(fpath)
                try:
                    mtime = os.path.getmtime(fpath)
                except OSError:
                    continue

                last_mtime = self._last_mtimes.get(fpath)
                if last_mtime is None or mtime > last_mtime:
                    changed.append(fpath)
                    self._last_mtimes[fpath] = mtime

        previously_known = set(self._last_mtimes.keys())
        removed = list(previously_known - current_files)
        for r in removed:
            del self._last_mtimes[r]

        return changed, removed
