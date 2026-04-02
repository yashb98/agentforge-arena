"""Async SQLite database with WAL mode — Team Bravo."""
from __future__ import annotations

import aiosqlite
from src.config import DATABASE_URL
from src.models import CREATE_TABLES_SQL

_connection: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Get or create the database connection."""
    global _connection
    if _connection is None:
        _connection = await aiosqlite.connect(DATABASE_URL)
        _connection.row_factory = aiosqlite.Row
        await _connection.execute("PRAGMA journal_mode=WAL")
        await _connection.execute("PRAGMA busy_timeout=5000")
        await _connection.executescript(CREATE_TABLES_SQL)
        await _connection.commit()
    return _connection


async def close_db() -> None:
    """Close the database connection."""
    global _connection
    if _connection is not None:
        await _connection.close()
        _connection = None


async def init_db(db_url: str | None = None) -> aiosqlite.Connection:
    """Initialize database, optionally with a custom URL."""
    global _connection
    _connection = await aiosqlite.connect(db_url or DATABASE_URL)
    _connection.row_factory = aiosqlite.Row
    await _connection.execute("PRAGMA journal_mode=WAL")
    await _connection.executescript(CREATE_TABLES_SQL)
    await _connection.commit()
    return _connection
