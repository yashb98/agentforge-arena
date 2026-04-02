"""Code Parser — Extract semantic chunks from source files via tree-sitter."""

from __future__ import annotations

import logging
import re

from packages.memory.src.indexer.grammars import GrammarLoader
from packages.memory.src.semantic.models import CodeChunk

logger = logging.getLogger(__name__)

# tree-sitter node types to extract per language
SYMBOL_NODE_TYPES: dict[str, set[str]] = {
    "python": {"function_definition", "class_definition"},
    "javascript": {"function_declaration", "class_declaration", "arrow_function", "export_statement"},
    "typescript": {"function_declaration", "class_declaration", "arrow_function", "export_statement"},
}

# Lines threshold: files shorter than this get a single chunk
SHORT_FILE_LINES = 50
# Sliding window for large files with no symbols
WINDOW_SIZE = 100
WINDOW_OVERLAP = 20


class CodeParser:
    """Extracts semantic code chunks from source files.

    Chunking strategy:
      - Files < 50 lines: single chunk (whole file)
      - Supported languages: extract function/class definitions via tree-sitter
      - Markdown: split by ## headings
      - Unsupported / no symbols: whole-file chunk
    """

    def __init__(self, grammar_loader: GrammarLoader) -> None:
        self._grammars = grammar_loader

    def parse(
        self,
        *,
        content: str,
        file_path: str,
        language: str,
        module_name: str,
    ) -> list[CodeChunk]:
        """Parse a source file into semantic chunks."""
        lines = content.split("\n")
        line_count = len(lines)

        # Short files → single chunk
        if line_count < SHORT_FILE_LINES:
            return [self._whole_file_chunk(content, file_path, language, module_name)]

        # Markdown → heading-based splits
        if language == "markdown":
            return self._parse_markdown(content, file_path, module_name)

        # Try tree-sitter for supported languages
        parser = self._grammars.get_parser(language)
        if parser is not None:
            chunks = self._parse_with_treesitter(
                parser, content, file_path, language, module_name
            )
            if chunks:
                return chunks

        # Fallback: whole-file chunk
        return [self._whole_file_chunk(content, file_path, language, module_name)]

    def _whole_file_chunk(
        self, content: str, file_path: str, language: str, module_name: str
    ) -> CodeChunk:
        """Create a single chunk for the entire file."""
        return CodeChunk(
            chunk_id=f"{file_path}::module",
            file_path=file_path,
            language=language,
            module_name=module_name,
            symbol_name=None,
            symbol_type="module",
            content=content,
            line_start=1,
            line_end=len(content.split("\n")),
        )

    def _parse_with_treesitter(
        self,
        parser: object,
        content: str,
        file_path: str,
        language: str,
        module_name: str,
    ) -> list[CodeChunk]:
        """Extract chunks using tree-sitter AST."""
        tree = parser.parse(content.encode())  # type: ignore[union-attr]
        node_types = SYMBOL_NODE_TYPES.get(language, set())
        chunks: list[CodeChunk] = []

        def visit(node: object) -> None:
            if node.type in node_types:  # type: ignore[union-attr]
                start_line = node.start_point[0] + 1  # type: ignore[union-attr]
                end_line = node.end_point[0] + 1  # type: ignore[union-attr]
                text = content.encode()[node.start_byte:node.end_byte].decode()  # type: ignore[union-attr]

                symbol_name = self._extract_name(node, language)
                symbol_type = self._node_type_to_symbol_type(node.type)  # type: ignore[union-attr]
                docstring = self._extract_docstring(node, language, content)

                chunks.append(
                    CodeChunk(
                        chunk_id=f"{file_path}::{symbol_name or f'chunk_{start_line}'}",
                        file_path=file_path,
                        language=language,
                        module_name=module_name,
                        symbol_name=symbol_name,
                        symbol_type=symbol_type,
                        content=text,
                        docstring=docstring,
                        line_start=start_line,
                        line_end=end_line,
                    )
                )

            for child in node.children:  # type: ignore[union-attr]
                visit(child)

        visit(tree.root_node)
        return chunks

    def _extract_name(self, node: object, language: str) -> str | None:
        """Extract the name identifier from a definition node."""
        for child in node.children:  # type: ignore[union-attr]
            if child.type == "identifier":  # type: ignore[union-attr]
                return child.text.decode()  # type: ignore[union-attr]
            if child.type == "name":  # type: ignore[union-attr]
                return child.text.decode()  # type: ignore[union-attr]
        return None

    def _node_type_to_symbol_type(self, node_type: str) -> str:
        """Map tree-sitter node type to our symbol_type enum."""
        if "class" in node_type:
            return "class"
        if "function" in node_type or "arrow" in node_type:
            return "function"
        if "export" in node_type:
            return "function"
        return "function"

    def _extract_docstring(
        self, node: object, language: str, content: str
    ) -> str | None:
        """Extract docstring from a Python function/class."""
        if language != "python":
            return None
        for child in node.children:  # type: ignore[union-attr]
            if child.type == "block":  # type: ignore[union-attr]
                for stmt in child.children:  # type: ignore[union-attr]
                    if stmt.type == "expression_statement":  # type: ignore[union-attr]
                        for expr in stmt.children:  # type: ignore[union-attr]
                            if expr.type == "string":  # type: ignore[union-attr]
                                raw = expr.text.decode()  # type: ignore[union-attr]
                                return raw.strip('"""').strip("'''").strip()
                        break
                break
        return None

    def _parse_markdown(
        self, content: str, file_path: str, module_name: str
    ) -> list[CodeChunk]:
        """Split markdown by ## headings."""
        sections: list[CodeChunk] = []
        current_heading: str | None = None
        current_lines: list[str] = []
        current_start = 1

        for i, line in enumerate(content.split("\n"), start=1):
            if line.startswith("## "):
                if current_lines:
                    section_content = "\n".join(current_lines)
                    name = current_heading or "intro"
                    sections.append(
                        CodeChunk(
                            chunk_id=f"{file_path}::{name}",
                            file_path=file_path,
                            language="markdown",
                            module_name=module_name,
                            symbol_name=name,
                            symbol_type="section",
                            content=section_content,
                            line_start=current_start,
                            line_end=i - 1,
                        )
                    )
                current_heading = line[3:].strip()
                current_lines = [line]
                current_start = i
            else:
                current_lines.append(line)

        if current_lines:
            name = current_heading or "intro"
            sections.append(
                CodeChunk(
                    chunk_id=f"{file_path}::{name}",
                    file_path=file_path,
                    language="markdown",
                    module_name=module_name,
                    symbol_name=name,
                    symbol_type="section",
                    content="\n".join(current_lines),
                    line_start=current_start,
                    line_end=current_start + len(current_lines) - 1,
                )
            )

        return sections if sections else [self._whole_file_chunk(content, file_path, "markdown", module_name)]
