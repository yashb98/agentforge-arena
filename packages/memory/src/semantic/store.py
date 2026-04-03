"""L3 semantic memory backed by a vector store client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uuid import UUID

    from packages.memory.src.indexer.parser import CodeChunk


class SemanticStore:
    """Adapter for storing and searching code chunks in vector DB."""

    def __init__(
        self,
        qdrant: Any,
        *,
        collection_prefix: str = "semantic_memory",
    ) -> None:
        self._qdrant = qdrant
        self._prefix = collection_prefix

    def collection_name(self, team_id: UUID) -> str:
        return f"{self._prefix}_{team_id}"

    async def upsert_chunks(
        self,
        *,
        team_id: UUID,
        chunks: list[CodeChunk],
        vectors: list[list[float]],
    ) -> None:
        points = []
        for idx, chunk in enumerate(chunks):
            points.append(
                {
                    "id": f"{chunk.file_path}:{chunk.symbol_name}:{idx}",
                    "vector": vectors[idx],
                    "payload": {
                        "file_path": chunk.file_path,
                        "language": chunk.language,
                        "symbol_name": chunk.symbol_name,
                        "symbol_type": chunk.symbol_type,
                        "content": chunk.content,
                    },
                }
            )
        await self._qdrant.upsert(self.collection_name(team_id), points)

    async def search(
        self,
        *,
        team_id: UUID,
        vector: list[float],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        rows = await self._qdrant.search(self.collection_name(team_id), vector, limit=limit)
        return list(rows)
