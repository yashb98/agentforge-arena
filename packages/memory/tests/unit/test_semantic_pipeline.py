"""Tests for semantic store and indexing pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from packages.memory.src.indexer.grammars import GrammarLoader
from packages.memory.src.indexer.parser import CodeParser
from packages.memory.src.indexer.pipeline import IndexingPipeline
from packages.memory.src.semantic.store import SemanticStore

if TYPE_CHECKING:
    from pathlib import Path


class _FakeQdrant:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[dict[str, object]]]] = []

    async def upsert(self, collection_name: str, points: list[dict[str, object]]) -> None:
        self.upserts.append((collection_name, points))

    async def search(
        self, collection_name: str, vector: list[float], *, limit: int
    ) -> list[dict[str, object]]:
        return [
            {
                "collection": collection_name,
                "limit": limit,
                "vector_size": len(vector),
            }
        ]


class _FakeEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]


@pytest.mark.asyncio
async def test_indexing_pipeline_upserts_chunks(tmp_path: Path) -> None:
    code_file = tmp_path / "service.py"
    code_file.write_text(
        "def run_task() -> None:\n"
        "    return None\n",
        encoding="utf-8",
    )
    parser = CodeParser(GrammarLoader())
    qdrant = _FakeQdrant()
    semantic = SemanticStore(qdrant)
    pipeline = IndexingPipeline(parser, semantic, _FakeEmbedder())

    inserted = await pipeline.index_files(team_id=uuid4(), files=[code_file])
    assert inserted > 0
    assert len(qdrant.upserts) == 1


@pytest.mark.asyncio
async def test_semantic_search_passthrough() -> None:
    qdrant = _FakeQdrant()
    semantic = SemanticStore(qdrant)
    rows = await semantic.search(team_id=uuid4(), vector=[1.0, 2.0], limit=3)
    assert rows[0]["limit"] == 3
