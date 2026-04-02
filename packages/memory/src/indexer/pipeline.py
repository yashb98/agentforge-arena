"""Indexing Pipeline — Parse -> embed -> upsert to Qdrant + L2 FILE_META."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from packages.memory.src.indexer.parser import CodeParser
from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.semantic.models import CodeChunk

logger = logging.getLogger(__name__)


class IndexingPipeline:
    """Orchestrates: parse files -> embed chunks -> upsert to Qdrant + L2."""

    def __init__(
        self,
        parser: CodeParser,
        embedder: object,
        semantic_store: object,
        module_store: object,
        team_id: UUID,
        tournament_id: UUID,
    ) -> None:
        self._parser = parser
        self._embedder = embedder
        self._semantic_store = semantic_store
        self._module_store = module_store
        self._team_id = team_id
        self._tournament_id = tournament_id
        self._grammar_loader = parser._grammars

    async def index_files(self, file_paths: list[str]) -> int:
        """Index a batch of files. Returns number of chunks indexed."""
        if not file_paths:
            return 0

        all_chunks: list[CodeChunk] = []
        file_meta_records: list[ModuleRecord] = []

        for file_path in file_paths:
            try:
                path = Path(file_path)
                if not path.exists():
                    logger.warning("File not found: %s", file_path)
                    continue

                content = path.read_text(errors="replace")
                ext = path.suffix
                language = self._grammar_loader.language_for_extension(ext)
                if language is None:
                    continue

                module_name = self._infer_module(file_path)
                chunks = self._parser.parse(
                    content=content,
                    file_path=file_path,
                    language=language,
                    module_name=module_name,
                )
                all_chunks.extend(chunks)

                # Create FILE_META record for L2
                file_meta_records.append(
                    ModuleRecord(
                        team_id=self._team_id,
                        tournament_id=self._tournament_id,
                        record_type=RecordType.FILE_META,
                        module_name=module_name,
                        file_path=file_path,
                        title=f"File: {path.name}",
                        content=f"{len(chunks)} chunks, {len(content.splitlines())} lines, language={language}",
                    ),
                )

            except Exception:
                logger.exception("Failed to index file: %s", file_path)

        if all_chunks:
            await self._semantic_store.upsert(all_chunks)  # type: ignore[union-attr]
        if file_meta_records:
            await self._module_store.insert_batch(file_meta_records)  # type: ignore[union-attr]

        logger.info("Indexed %d chunks from %d files", len(all_chunks), len(file_paths))
        return len(all_chunks)

    async def remove_files(self, file_paths: list[str]) -> None:
        """Remove indexed data for deleted files."""
        for file_path in file_paths:
            await self._semantic_store.delete_by_file(file_path)  # type: ignore[union-attr]

    def _infer_module(self, file_path: str) -> str:
        """Infer module name from file path."""
        parts = file_path.replace("\\", "/").split("/")
        for i, part in enumerate(parts):
            if part == "src" and i + 1 < len(parts):
                return parts[i + 1].replace(".py", "").replace(".ts", "")
        if len(parts) >= 2:
            return parts[-2]
        return "root"
