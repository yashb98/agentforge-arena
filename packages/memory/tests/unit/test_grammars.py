"""Tests for GrammarLoader (lazy tree-sitter grammar loading)."""

from __future__ import annotations

from packages.memory.src.indexer.grammars import GrammarLoader


class TestGrammarLoader:
    """Tests for lazy grammar loading."""

    def test_extension_to_language_mapping(self) -> None:
        """Common extensions should map to languages."""
        loader = GrammarLoader()
        assert loader.language_for_extension(".py") == "python"
        assert loader.language_for_extension(".ts") == "typescript"
        assert loader.language_for_extension(".tsx") == "typescript"
        assert loader.language_for_extension(".js") == "javascript"
        assert loader.language_for_extension(".jsx") == "javascript"

    def test_unknown_extension_returns_none(self) -> None:
        """Unknown extensions should return None."""
        loader = GrammarLoader()
        assert loader.language_for_extension(".xyz") is None
        assert loader.language_for_extension(".csv") is None

    def test_supported_extensions(self) -> None:
        """Should list all supported extensions."""
        loader = GrammarLoader()
        exts = loader.supported_extensions()
        assert ".py" in exts
        assert ".ts" in exts
        assert ".js" in exts
        assert ".md" in exts

    def test_get_parser_returns_parser(self) -> None:
        """get_parser() should return a tree-sitter Parser for known language."""
        loader = GrammarLoader()
        parser = loader.get_parser("python")
        assert parser is not None

    def test_get_parser_caches(self) -> None:
        """get_parser() should cache parsers after first load."""
        loader = GrammarLoader()
        p1 = loader.get_parser("python")
        p2 = loader.get_parser("python")
        assert p1 is p2

    def test_get_parser_unknown_returns_none(self) -> None:
        """get_parser() for unknown language should return None."""
        loader = GrammarLoader()
        assert loader.get_parser("cobol") is None
