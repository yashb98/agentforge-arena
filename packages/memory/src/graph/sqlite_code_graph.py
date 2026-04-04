"""Persist parsed code chunks and import edges in SQLite (per workspace graph file)."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from packages.memory.src.indexer.module_graph import ModuleGraphBuilder

if TYPE_CHECKING:
    from packages.memory.src.indexer.parser import CodeChunk

_SCHEMA = """
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    symbol_name TEXT NOT NULL,
    symbol_type TEXT NOT NULL,
    language TEXT NOT NULL,
    content_preview TEXT NOT NULL,
    content_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_symbols_team_file ON symbols (team_id, file_path);
CREATE INDEX IF NOT EXISTS idx_symbols_team_name ON symbols (team_id, symbol_name);

CREATE TABLE IF NOT EXISTS import_edges (
    team_id TEXT NOT NULL,
    from_file TEXT NOT NULL,
    to_module TEXT NOT NULL,
    PRIMARY KEY (team_id, from_file, to_module)
);

CREATE VIRTUAL TABLE IF NOT EXISTS symbol_fts USING fts5(
    team_id UNINDEXED,
    file_path,
    symbol_name,
    symbol_type UNINDEXED,
    content_preview,
    tokenize = 'porter unicode61'
);
"""


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


class CodeKnowledgeGraph:
    """AST-oriented chunk store + import graph + FTS5 over symbol text."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)

    def _conn(self) -> sqlite3.Connection:
        return _connect(self._path)

    def clear_team(self, team_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM import_edges WHERE team_id = ?", (team_id,))
            c.execute("DELETE FROM symbols WHERE team_id = ?", (team_id,))
            c.execute("DELETE FROM symbol_fts WHERE team_id = ?", (team_id,))

    def rebuild_team(self, team_id: str, chunks: list[CodeChunk]) -> None:
        """Replace team rows with *chunks* and derived import edges."""
        self.clear_team(team_id)
        graph = ModuleGraphBuilder().build(chunks)
        with self._conn() as c:
            for ch in chunks:
                preview = ch.content[:4000]
                h = hashlib.sha256(ch.content.encode()).hexdigest()[:32]
                cur = c.execute(
                    """
                    INSERT INTO symbols (
                        team_id, file_path, symbol_name, symbol_type, language,
                        content_preview, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        team_id,
                        ch.file_path,
                        ch.symbol_name,
                        ch.symbol_type,
                        ch.language,
                        preview,
                        h,
                    ),
                )
                row_id = cur.lastrowid
                c.execute(
                    """
                    INSERT INTO symbol_fts (
                        rowid, team_id, file_path, symbol_name, symbol_type, content_preview
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row_id,
                        team_id,
                        ch.file_path,
                        ch.symbol_name,
                        ch.symbol_type,
                        preview,
                    ),
                )
            for from_file, deps in graph.items():
                for dep in deps:
                    c.execute(
                        """
                        INSERT OR IGNORE INTO import_edges (team_id, from_file, to_module)
                        VALUES (?, ?, ?)
                        """,
                        (team_id, from_file, dep),
                    )

    def search_fts(self, team_id: str, query: str, *, limit: int = 20) -> list[dict[str, str]]:
        """BM25-style FTS over symbol previews (SQLite FTS5)."""
        q = query.strip()
        if not q:
            return []
        with self._conn() as c:
            cur = c.execute(
                """
                SELECT file_path, symbol_name, symbol_type, bm25(symbol_fts) AS rank
                FROM symbol_fts
                WHERE team_id = ? AND symbol_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (team_id, q, limit),
            )
            rows = cur.fetchall()
        return [
            {
                "file_path": r["file_path"],
                "symbol_name": r["symbol_name"],
                "symbol_type": r["symbol_type"],
                "rank": float(r["rank"]),
            }
            for r in rows
        ]

    def list_edges(self, team_id: str, *, limit: int = 500) -> list[tuple[str, str]]:
        with self._conn() as c:
            cur = c.execute(
                """
                SELECT from_file, to_module FROM import_edges
                WHERE team_id = ? LIMIT ?
                """,
                (team_id, limit),
            )
            return [(r[0], r[1]) for r in cur.fetchall()]
