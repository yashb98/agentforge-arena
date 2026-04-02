"""Message storage and retrieval — Team Bravo."""
from __future__ import annotations
from src.database import get_db
from src.models import MessageResponse, PaginatedMessages


async def save_message(room_id: int, username: str, content: str) -> MessageResponse:
    """Persist a chat message."""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO messages (room_id, username, content) VALUES (?, ?, ?)",
        (room_id, username, content),
    )
    await db.commit()
    row = await (await db.execute("SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,))).fetchone()
    return MessageResponse(id=row["id"], room_id=row["room_id"], username=row["username"],
                           content=row["content"], created_at=str(row["created_at"]))


async def get_messages(room_id: int, limit: int = 50, offset: int = 0) -> PaginatedMessages:
    """Get paginated message history for a room."""
    db = await get_db()
    total_row = await (await db.execute("SELECT COUNT(*) as c FROM messages WHERE room_id = ?", (room_id,))).fetchone()
    rows = await (await db.execute(
        "SELECT * FROM messages WHERE room_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
        (room_id, limit, offset),
    )).fetchall()
    msgs = [MessageResponse(id=r["id"], room_id=r["room_id"], username=r["username"],
                            content=r["content"], created_at=str(r["created_at"])) for r in rows]
    return PaginatedMessages(messages=msgs, total=total_row["c"], limit=limit, offset=offset)


async def search_messages(room_id: int, keyword: str) -> list[MessageResponse]:
    """Search messages by keyword in a room."""
    db = await get_db()
    rows = await (await db.execute(
        "SELECT * FROM messages WHERE room_id = ? AND content LIKE ? ORDER BY created_at DESC",
        (room_id, f"%{keyword}%"),
    )).fetchall()
    return [MessageResponse(id=r["id"], room_id=r["room_id"], username=r["username"],
                            content=r["content"], created_at=str(r["created_at"])) for r in rows]
