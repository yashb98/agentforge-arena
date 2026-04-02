"""L3 Semantic Store — Qdrant vector search over codebase."""

from __future__ import annotations

import logging
from uuid import UUID

from qdrant_client import models
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    VectorParams,
)

from packages.memory.src.semantic.models import CodeChunk, SearchResult

logger = logging.getLogger(__name__)


class SemanticStore:
    """Qdrant-backed semantic search over team codebase.

    Uses named vectors (code, docstring) + sparse vectors (keywords).
    INT8 quantization keeps 100k LOC index under 100MB RAM.
    """

    def __init__(
        self,
        qdrant: object,
        embedder: object,
        team_id: UUID,
    ) -> None:
        self._qdrant = qdrant
        self._embedder = embedder
        self._team_id = team_id

    @property
    def collection_name(self) -> str:
        return f"code_search_{self._team_id}"

    async def ensure_collection(self) -> None:
        """Create Qdrant collection if it doesn't exist."""
        exists = await self._qdrant.collection_exists(self.collection_name)  # type: ignore[union-attr]
        if exists:
            return

        await self._qdrant.create_collection(  # type: ignore[union-attr]
            collection_name=self.collection_name,
            vectors_config={
                "code": VectorParams(size=384, distance=Distance.COSINE),
                "docstring": VectorParams(size=384, distance=Distance.COSINE),
            },
            quantization_config=ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,
                ),
            ),
        )
        logger.info("Created Qdrant collection: %s", self.collection_name)

    async def upsert(self, chunks: list[CodeChunk]) -> None:
        """Upsert code chunks with embeddings into Qdrant."""
        if not chunks:
            return

        contents = [c.content for c in chunks]
        embeddings = await self._embedder.embed_bulk(contents)  # type: ignore[union-attr]

        points = []
        for chunk, embedding in zip(chunks, embeddings):
            payload = {
                "file_path": chunk.file_path,
                "language": chunk.language,
                "module_name": chunk.module_name,
                "symbol_name": chunk.symbol_name,
                "symbol_type": chunk.symbol_type,
                "content": chunk.content,
                "line_start": chunk.line_start,
                "line_end": chunk.line_end,
                "dependencies": chunk.dependencies,
            }

            vectors = {"code": embedding}
            if chunk.docstring:
                ds_emb = await self._embedder.embed_query(chunk.docstring)  # type: ignore[union-attr]
                vectors["docstring"] = ds_emb

            points.append(
                PointStruct(
                    id=chunk.chunk_id,
                    vector=vectors,
                    payload=payload,
                )
            )

        await self._qdrant.upsert(  # type: ignore[union-attr]
            collection_name=self.collection_name,
            points=points,
        )
        logger.debug("Upserted %d chunks to %s", len(points), self.collection_name)

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        file_filter: str | None = None,
    ) -> list[SearchResult]:
        """Search for code chunks matching a natural language query."""
        query_embedding = await self._embedder.embed_query(query)  # type: ignore[union-attr]

        search_filter = None
        if file_filter:
            search_filter = Filter(
                must=[FieldCondition(key="file_path", match=MatchValue(value=file_filter))]
            )

        points = await self._qdrant.search(  # type: ignore[union-attr]
            collection_name=self.collection_name,
            query_vector=("code", query_embedding),
            limit=limit,
            query_filter=search_filter,
            with_payload=True,
        )

        results = []
        for point in points:
            payload = point.payload or {}
            chunk = CodeChunk(
                chunk_id=str(point.id),
                file_path=payload.get("file_path", ""),
                language=payload.get("language", ""),
                module_name=payload.get("module_name", ""),
                symbol_name=payload.get("symbol_name"),
                symbol_type=payload.get("symbol_type"),
                content=payload.get("content", ""),
                line_start=payload.get("line_start", 0),
                line_end=payload.get("line_end", 0),
                dependencies=payload.get("dependencies", []),
            )
            snippet = (
                f"{chunk.file_path}:{chunk.line_start}-{chunk.line_end}"
                f" {chunk.symbol_name or 'chunk'}"
            )
            results.append(
                SearchResult(
                    source="semantic",
                    score=point.score,
                    chunk=chunk,
                    snippet=snippet,
                )
            )

        return results

    async def delete_by_file(self, file_path: str) -> None:
        """Delete all points for a given file."""
        await self._qdrant.delete(  # type: ignore[union-attr]
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
                )
            ),
        )
        logger.debug("Deleted points for file: %s", file_path)

    async def delete_collection(self) -> None:
        """Delete the entire collection. Used at tournament end."""
        await self._qdrant.delete_collection(self.collection_name)  # type: ignore[union-attr]
        logger.info("Deleted Qdrant collection: %s", self.collection_name)
