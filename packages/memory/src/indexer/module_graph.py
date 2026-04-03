"""Module graph utilities for navigation and dependency mapping."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.memory.src.indexer.parser import CodeChunk


class ModuleGraphBuilder:
    """Builds a simple module dependency graph from code chunks."""

    _IMPORT_RE = re.compile(r"^\s*import\s+([a-zA-Z0-9_\.]+)", re.MULTILINE)
    _FROM_RE = re.compile(r"^\s*from\s+([a-zA-Z0-9_\.]+)\s+import\s+", re.MULTILINE)

    def build(self, chunks: list[CodeChunk]) -> dict[str, list[str]]:
        graph: dict[str, set[str]] = defaultdict(set)
        for chunk in chunks:
            module = chunk.file_path
            imports = self._IMPORT_RE.findall(chunk.content) + self._FROM_RE.findall(
                chunk.content
            )
            for dep in imports:
                graph[module].add(dep)
            if module not in graph:
                graph[module] = set()
        return {module: sorted(deps) for module, deps in graph.items()}
