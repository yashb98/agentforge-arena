"""Codebase navigation service for agent tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from packages.memory.src.indexer.module_graph import ModuleGraphBuilder
from packages.memory.src.indexer.parser import CodeChunk, CodeParser

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID


@dataclass(slots=True)
class SymbolHit:
    file_path: str
    symbol_name: str
    symbol_type: str


@dataclass(slots=True)
class UsageHit:
    file_path: str
    line: int
    snippet: str


class NavigationService:
    """Provides symbol lookup, usage lookup, and module graph summaries."""

    def __init__(self, parser: CodeParser) -> None:
        self._parser = parser
        self._module_graph = ModuleGraphBuilder()

    def _parse_files(self, files: Sequence[str]) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        for file_path in files:
            chunks.extend(self._parser.parse_file(file_path))
        return chunks

    async def find_symbol(
        self,
        *,
        team_id: UUID,  # reserved for future store partitioning
        files: Sequence[str],
        symbol: str,
    ) -> list[SymbolHit]:
        _ = team_id
        hits: list[SymbolHit] = []
        for chunk in self._parse_files(files):
            if chunk.symbol_name == symbol:
                hits.append(
                    SymbolHit(
                        file_path=chunk.file_path,
                        symbol_name=chunk.symbol_name,
                        symbol_type=chunk.symbol_type,
                    )
                )
        return hits

    async def where_used(
        self,
        *,
        team_id: UUID,  # reserved for future store partitioning
        files: Sequence[str],
        symbol: str,
    ) -> list[UsageHit]:
        _ = team_id
        usages: list[UsageHit] = []
        for file_path in files:
            path = Path(file_path)
            if not path.is_file():
                continue
            for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if symbol not in line:
                    continue
                stripped = line.strip()
                if stripped.startswith("def ") or stripped.startswith("class "):
                    continue
                usages.append(UsageHit(file_path=str(path), line=idx, snippet=stripped))
        return usages

    async def module_map(
        self,
        *,
        team_id: UUID,  # reserved for future store partitioning
        files: Sequence[str],
    ) -> dict[str, list[str]]:
        _ = team_id
        chunks: list[CodeChunk] = []
        for file_path in files:
            path = Path(file_path)
            if not path.is_file():
                continue
            chunks.append(
                CodeChunk(
                    file_path=str(path),
                    language="text",
                    symbol_name=path.stem,
                    symbol_type="file",
                    content=path.read_text(encoding="utf-8"),
                )
            )
        return self._module_graph.build(chunks)
