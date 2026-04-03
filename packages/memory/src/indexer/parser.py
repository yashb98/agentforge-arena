"""Code parser that emits semantic chunks for indexing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class GrammarLoaderProtocol(Protocol):
    def detect_language(self, path: str | Path) -> str:
        ...


@dataclass(slots=True)
class CodeChunk:
    """A semantic chunk extracted from source text."""

    file_path: str
    language: str
    symbol_name: str
    symbol_type: str
    content: str


class CodeParser:
    """Extracts simple function/class chunks from code files."""

    def __init__(self, grammar_loader: GrammarLoaderProtocol) -> None:
        self._grammars = grammar_loader

    def parse_file(self, file_path: str | Path) -> list[CodeChunk]:
        path = Path(file_path)
        if not path.is_file():
            return []
        language = self._grammars.detect_language(path)
        content = path.read_text(encoding="utf-8")
        if language == "python":
            chunks = self._parse_python(path, content)
            if chunks:
                return chunks
        return [
            CodeChunk(
                file_path=str(path),
                language=language,
                symbol_name=path.stem,
                symbol_type="file",
                content=content,
            )
        ]

    def _parse_python(self, path: Path, content: str) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        pattern = re.compile(r"^(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
        lines = content.splitlines()
        for match in pattern.finditer(content):
            symbol_type = "class" if match.group(1) == "class" else "function"
            symbol_name = match.group(2)
            start_idx = content[: match.start()].count("\n")
            end_idx = min(len(lines), start_idx + 40)
            snippet = "\n".join(lines[start_idx:end_idx])
            chunks.append(
                CodeChunk(
                    file_path=str(path),
                    language="python",
                    symbol_name=symbol_name,
                    symbol_type=symbol_type,
                    content=snippet,
                )
            )
        return chunks
