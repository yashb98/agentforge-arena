"""Async SQLite database manager."""
from __future__ import annotations

import aiosqlite
from src.config import DATABASE_URL
from src.models import CREATE_TABLES_SQL

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Get the database connection, creating if needed."""
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DATABASE_URL)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA busy_timeout=5000")
        await _db.executescript(CREATE_TABLES_SQL)
        await _db.commit()
    return _db


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def init_db(db_url: str | None = None) -> aiosqlite.Connection:
    """Initialize DB with optional custom URL (for testing)."""
    global _db
    url = db_url or DATABASE_URL
    _db = await aiosqlite.connect(url)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.executescript(CREATE_TABLES_SQL)
    await _db.commit()
    return _db
