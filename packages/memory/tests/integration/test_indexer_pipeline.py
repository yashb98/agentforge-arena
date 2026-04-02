"""Integration tests for IndexingPipeline (parse -> embed -> upsert)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from packages.memory.src.indexer.grammars import GrammarLoader
from packages.memory.src.indexer.parser import CodeParser
from packages.memory.src.indexer.pipeline import IndexingPipeline


@pytest.fixture()
def mock_semantic_store():
    store = MagicMock()
    store.upsert = AsyncMock()
    store.delete_by_file = AsyncMock()
    return store


@pytest.fixture()
def mock_module_store():
    store = MagicMock()
    store.insert_batch = AsyncMock()
    return store


@pytest.fixture()
def pipeline(mock_semantic_store, mock_module_store, team_id, tournament_id):
    grammar_loader = GrammarLoader()
    parser = CodeParser(grammar_loader=grammar_loader)
    mock_embedder = MagicMock()
    mock_embedder.embed_bulk = AsyncMock(return_value=[[0.1] * 384])
    return IndexingPipeline(
        parser=parser,
        embedder=mock_embedder,
        semantic_store=mock_semantic_store,
        module_store=mock_module_store,
        team_id=team_id,
        tournament_id=tournament_id,
    )


@pytest.fixture()
def workspace(tmp_path) -> Path:
    """Create a workspace with sample files."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text(
        'def login(user, pw):\n    """Login."""\n    return "ok"\n'
    )
    (tmp_path / "src" / "main.py").write_text('print("hello")\n')
    return tmp_path


class TestIndexingPipeline:
    """Integration tests for the indexing pipeline."""

    @pytest.mark.asyncio
    async def test_index_files_upserts_to_qdrant(
        self, pipeline, mock_semantic_store, workspace
    ) -> None:
        """index_files() should parse, embed, and upsert to Qdrant."""
        files = [str(workspace / "src" / "auth.py")]
        await pipeline.index_files(files)
        mock_semantic_store.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_files_creates_file_meta_records(
        self, pipeline, mock_module_store, workspace
    ) -> None:
        """index_files() should create FILE_META records in L2."""
        files = [str(workspace / "src" / "auth.py")]
        await pipeline.index_files(files)
        mock_module_store.insert_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_empty_list_is_noop(
        self, pipeline, mock_semantic_store
    ) -> None:
        """index_files([]) should not call upsert."""
        await pipeline.index_files([])
        mock_semantic_store.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_deleted_files(
        self, pipeline, mock_semantic_store
    ) -> None:
        """remove_files() should delete from Qdrant."""
        await pipeline.remove_files(["src/old_file.py"])
        mock_semantic_store.delete_by_file.assert_called_once_with("src/old_file.py")
