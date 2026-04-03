"""Unit tests for grammar loader, parser, and watcher."""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.memory.src.indexer.grammars import GrammarLoader
from packages.memory.src.indexer.parser import CodeParser
from packages.memory.src.indexer.watcher import CodebaseWatcher

if TYPE_CHECKING:
    from pathlib import Path


def test_grammar_loader_detects_language() -> None:
    loader = GrammarLoader()
    assert loader.detect_language("x.py") == "python"
    assert loader.detect_language("x.ts") == "typescript"
    assert loader.detect_language("x.unknown") == "text"


def test_code_parser_extracts_python_symbols(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "class MyService:\n"
        "    pass\n\n"
        "def do_work() -> None:\n"
        "    return None\n",
        encoding="utf-8",
    )
    parser = CodeParser(GrammarLoader())
    chunks = parser.parse_file(file_path)
    names = {chunk.symbol_name for chunk in chunks}
    assert "MyService" in names
    assert "do_work" in names


def test_watcher_reports_incremental_changes(tmp_path: Path) -> None:
    file_path = tmp_path / "a.py"
    file_path.write_text("print('a')", encoding="utf-8")
    watcher = CodebaseWatcher()
    first = watcher.changed_files([file_path])
    second = watcher.changed_files([file_path])
    file_path.write_text("print('b')", encoding="utf-8")
    third = watcher.changed_files([file_path])
    assert first == [str(file_path)]
    assert second == []
    assert third == [str(file_path)]
