"""Grammar Loader — Lazy-load tree-sitter grammars per language."""

from __future__ import annotations

import logging

import tree_sitter

logger = logging.getLogger(__name__)

# Extension → language mapping
EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".md": "markdown",
}

# Language → tree-sitter grammar module import path
GRAMMAR_MODULES: dict[str, str] = {
    "python": "tree_sitter_python",
    "javascript": "tree_sitter_javascript",
    "typescript": "tree_sitter_typescript.tsx",
}


class GrammarLoader:
    """Lazy-loads and caches tree-sitter grammars per language."""

    def __init__(self) -> None:
        self._parsers: dict[str, tree_sitter.Parser] = {}

    def language_for_extension(self, ext: str) -> str | None:
        """Map file extension to language name. Returns None if unsupported."""
        return EXTENSION_MAP.get(ext)

    def supported_extensions(self) -> set[str]:
        """Return all supported file extensions."""
        return set(EXTENSION_MAP.keys())

    def get_parser(self, language: str) -> tree_sitter.Parser | None:
        """Get or create a tree-sitter Parser for a language."""
        if language in self._parsers:
            return self._parsers[language]

        module_path = GRAMMAR_MODULES.get(language)
        if module_path is None:
            if language == "markdown":
                return None
            logger.debug("No grammar module for language: %s", language)
            return None

        try:
            import importlib

            mod = importlib.import_module(module_path)
            lang = tree_sitter.Language(mod.language())
            parser = tree_sitter.Parser(lang)
            self._parsers[language] = parser
            logger.info("Loaded tree-sitter grammar: %s", language)
            return parser
        except Exception:
            logger.warning("Failed to load tree-sitter grammar: %s", language, exc_info=True)
            return None
