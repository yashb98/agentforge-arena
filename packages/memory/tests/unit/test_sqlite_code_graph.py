"""SQLite code knowledge graph."""

from __future__ import annotations

from pathlib import Path

from packages.memory.src.graph.sqlite_code_graph import CodeKnowledgeGraph
from packages.memory.src.indexer.parser import CodeChunk


def test_rebuild_and_fts_search(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    g = CodeKnowledgeGraph(db)
    team = "team-a"
    chunks = [
        CodeChunk(
            file_path=str(tmp_path / "m.py"),
            language="python",
            symbol_name="hello",
            symbol_type="function",
            content="def hello():\n    return 'world'\n",
        ),
    ]
    g.rebuild_team(team, chunks)
    hits = g.search_fts(team, "hello")
    assert hits
    assert hits[0]["symbol_name"] == "hello"
    edges = g.list_edges(team)
    assert isinstance(edges, list)
