"""Parse -> embed -> upsert pipeline for semantic code memory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from packages.memory.src.indexer.parser import CodeChunk


class EmbedderProtocol(Protocol):
    """Embedding adapter used by indexing pipeline."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class ParserProtocol(Protocol):
    def parse_file(self, file_path: str) -> list[CodeChunk]:
        ...


class SemanticStoreProtocol(Protocol):
    async def upsert_chunks(
        self,
        *,
        team_id: UUID,
        chunks: list[CodeChunk],
        vectors: list[list[float]],
    ) -> None:
        ...


class IndexingPipeline:
    """Runs end-to-end indexing for a list of files."""

    def __init__(
        self,
        parser: ParserProtocol,
        semantic_store: SemanticStoreProtocol,
        embedder: EmbedderProtocol,
    ) -> None:
        self._parser = parser
        self._semantic = semantic_store
        self._embedder = embedder

    async def index_files(self, *, team_id: UUID, files: list[str]) -> int:
        chunks: list[Any] = []
        for file_path in files:
            chunks.extend(self._parser.parse_file(file_path))
        if not chunks:
            return 0

        vectors = await self._embedder.embed([chunk.content for chunk in chunks])
        await self._semantic.upsert_chunks(team_id=team_id, chunks=chunks, vectors=vectors)
        return len(chunks)
