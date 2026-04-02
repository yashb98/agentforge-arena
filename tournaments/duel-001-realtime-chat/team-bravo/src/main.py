"""FastAPI application — Team Bravo Real-Time Chat (Event-Driven)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from src.database import close_db, init_db
from src.models import MessageCreate, PaginatedMessages, RoomCreate, RoomResponse
from src import messages, rooms
from src.presence import presence
from src.websocket_manager import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle — init DB on startup."""
    await init_db()
    logger.info("Chat Bravo ready")
    yield
    await close_db()


app = FastAPI(title="Team Bravo Chat", version="1.0.0", lifespan=lifespan)


# ---- REST: Rooms ----

@app.post("/rooms", response_model=RoomResponse, status_code=201)
async def create_room_endpoint(body: RoomCreate) -> RoomResponse:
    """Create a new chat room."""
    try:
        return await rooms.create_room(body.name)
    except Exception:
        raise HTTPException(409, detail=f"Room '{body.name}' already exists")


@app.get("/rooms", response_model=list[RoomResponse])
async def list_rooms_endpoint() -> list[RoomResponse]:
    """List all rooms."""
    return await rooms.list_rooms()


@app.get("/rooms/{room_id}", response_model=RoomResponse)
async def get_room_endpoint(room_id: int) -> RoomResponse:
    """Get room details."""
    room = await rooms.get_room(room_id)
    if not room:
        raise HTTPException(404, detail="Room not found")
    return room


@app.post("/rooms/{room_id}/join")
async def join_room_endpoint(room_id: int, username: str = Query(...)) -> dict:
    """Join a room."""
    room = await rooms.get_room(room_id)
    if not room:
        raise HTTPException(404, detail="Room not found")
    ok = await rooms.join_room(room_id, username)
    return {"joined": ok, "room_id": room_id, "username": username}


@app.post("/rooms/{room_id}/leave")
async def leave_room_endpoint(room_id: int, username: str = Query(...)) -> dict:
    """Leave a room."""
    ok = await rooms.leave_room(room_id, username)
    return {"left": ok, "room_id": room_id, "username": username}


# ---- REST: Messages ----

@app.get("/rooms/{room_id}/messages", response_model=PaginatedMessages)
async def get_messages_endpoint(
    room_id: int, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
) -> PaginatedMessages:
    """Paginated message history."""
    return await messages.get_messages(room_id, limit=limit, offset=offset)


@app.get("/rooms/{room_id}/messages/search")
async def search_messages_endpoint(room_id: int, q: str = Query(..., min_length=1)) -> list:
    """Search messages by keyword."""
    results = await messages.search_messages(room_id, q)
    return [r.model_dump() for r in results]


# ---- REST: Presence ----

@app.get("/presence")
async def get_all_presence() -> dict:
    """Get all online users."""
    return {"rooms": {str(rid): users for rid, users in _build_presence().items()}}


@app.get("/rooms/{room_id}/presence")
async def get_room_presence_endpoint(room_id: int) -> dict:
    """Get online users in a room."""
    return {"room_id": room_id, "online_users": presence.get_online(room_id)}


def _build_presence() -> dict[int, list[str]]:
    """Build full presence map."""
    result = {}
    for rid in list(presence._rooms.keys()):
        result[rid] = presence.get_online(rid)
    return result


# ---- WebSocket (Event-Driven Dispatch) ----

async def _handle_join(username: str, data: dict) -> None:
    """Handle join_room event."""
    room_id = data["room_id"]
    manager.add_to_room(room_id, username)
    presence.join(room_id, username)
    await rooms.join_room(room_id, username)
    await manager.emit(room_id, {
        "type": "system",
        "data": {"message": f"{username} joined", "username": username, "room_id": room_id},
    })


async def _handle_leave(username: str, data: dict) -> None:
    """Handle leave_room event."""
    room_id = data["room_id"]
    manager.remove_from_room(room_id, username)
    presence.leave(room_id, username)
    await rooms.leave_room(room_id, username)
    await manager.emit(room_id, {
        "type": "system",
        "data": {"message": f"{username} left", "username": username, "room_id": room_id},
    })


async def _handle_message(username: str, data: dict) -> None:
    """Handle send_message event."""
    room_id = data["room_id"]
    content = data["content"]
    msg = await messages.save_message(room_id, username, content)
    await manager.emit(room_id, {"type": "message", "data": msg.model_dump()})


async def _handle_typing(username: str, data: dict) -> None:
    """Handle typing indicator event."""
    room_id = data["room_id"]
    is_typing = data.get("is_typing", True)
    await manager.emit(room_id, {
        "type": "typing",
        "data": {"username": username, "room_id": room_id, "is_typing": is_typing},
    }, skip=username)


async def _handle_dm(username: str, ws: WebSocket, data: dict) -> None:
    """Handle direct message event."""
    to_user = data["to_username"]
    content = data["content"]
    sent = await manager.send_dm(to_user, {
        "type": "dm", "data": {"from": username, "content": content},
    })
    if not sent:
        await ws.send_json({"type": "system", "data": {"message": f"{to_user} is not online"}})


_HANDLERS = {
    "join_room": lambda u, ws, d: _handle_join(u, d),
    "leave_room": lambda u, ws, d: _handle_leave(u, d),
    "send_message": lambda u, ws, d: _handle_message(u, d),
    "typing": lambda u, ws, d: _handle_typing(u, d),
    "dm": lambda u, ws, d: _handle_dm(u, ws, d),
}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, username: str = Query(...)) -> None:
    """WebSocket endpoint — dispatches events to typed handlers."""
    await manager.connect(websocket, username)
    logger.info("WS connected: %s", username)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")
            handler = _HANDLERS.get(msg_type)
            if handler:
                await handler(username, websocket, data)
            else:
                await websocket.send_json({
                    "type": "system",
                    "data": {"message": f"Unknown message type: {msg_type}"},
                })
    except WebSocketDisconnect:
        logger.info("WS disconnected: %s", username)
    except Exception as exc:
        logger.error("WS error for %s: %s", username, exc)
    finally:
        affected = manager.disconnect(username)
        rooms_gone = presence.disconnect(username)
        for rid in rooms_gone:
            await manager.emit(rid, {
                "type": "system",
                "data": {"message": f"{username} went offline", "username": username, "room_id": rid},
            })


if __name__ == "__main__":
    import uvicorn
    from src.config import HOST, PORT
    uvicorn.run("src.main:app", host=HOST, port=PORT, reload=True)
