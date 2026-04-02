"""Room management — CRUD operations."""
from __future__ import annotations
from src.database import get_db
from src.models import RoomResponse


async def create_room(name: str) -> RoomResponse:
    """Create a new chat room."""
    db = await get_db()
    cursor = await db.execute("INSERT INTO rooms (name) VALUES (?)", (name,))
    await db.commit()
    row = await (await db.execute("SELECT * FROM rooms WHERE id = ?", (cursor.lastrowid,))).fetchone()
    return RoomResponse(id=row["id"], name=row["name"], created_at=str(row["created_at"]), member_count=0)


async def get_room(room_id: int) -> RoomResponse | None:
    """Get a room by ID."""
    db = await get_db()
    row = await (await db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))).fetchone()
    if row is None:
        return None
    count = await (await db.execute("SELECT COUNT(*) as c FROM room_members WHERE room_id = ?", (room_id,))).fetchone()
    return RoomResponse(id=row["id"], name=row["name"], created_at=str(row["created_at"]), member_count=count["c"])


async def list_rooms() -> list[RoomResponse]:
    """List all rooms with member counts."""
    db = await get_db()
    rows = await (await db.execute(
        "SELECT r.*, COALESCE(m.cnt, 0) as member_count FROM rooms r "
        "LEFT JOIN (SELECT room_id, COUNT(*) as cnt FROM room_members GROUP BY room_id) m "
        "ON r.id = m.room_id ORDER BY r.created_at DESC"
    )).fetchall()
    return [RoomResponse(id=r["id"], name=r["name"], created_at=str(r["created_at"]), member_count=r["member_count"]) for r in rows]


async def join_room(room_id: int, username: str) -> bool:
    """Add a user to a room. Returns True if newly joined."""
    db = await get_db()
    try:
        await db.execute("INSERT INTO room_members (room_id, username) VALUES (?, ?)", (room_id, username))
        await db.commit()
        return True
    except Exception:
        return False


async def leave_room(room_id: int, username: str) -> bool:
    """Remove a user from a room."""
    db = await get_db()
    cursor = await db.execute("DELETE FROM room_members WHERE room_id = ? AND username = ?", (room_id, username))
    await db.commit()
    return cursor.rowcount > 0
