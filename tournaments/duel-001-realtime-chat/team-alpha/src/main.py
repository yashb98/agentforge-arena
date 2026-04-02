"""FastAPI application — Team Alpha Real-Time Chat."""
from __future__ import annotations

import json
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
    """Initialize and clean up resources."""
    await init_db()
    logger.info("Database initialized")
    yield
    await close_db()
    logger.info("Database closed")


app = FastAPI(title="Team Alpha Chat", version="1.0.0", lifespan=lifespan)


# ---- REST: Rooms ----

@app.post("/rooms", response_model=RoomResponse, status_code=201)
async def create_room_endpoint(body: RoomCreate) -> RoomResponse:
    """Create a new chat room."""
    try:
        return await rooms.create_room(body.name)
    except Exception:
        raise HTTPException(status_code=409, detail=f"Room '{body.name}' already exists")


@app.get("/rooms", response_model=list[RoomResponse])
async def list_rooms_endpoint() -> list[RoomResponse]:
    """List all rooms with member counts."""
    return await rooms.list_rooms()


@app.get("/rooms/{room_id}", response_model=RoomResponse)
async def get_room_endpoint(room_id: int) -> RoomResponse:
    """Get a room by ID."""
    room = await rooms.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@app.post("/rooms/{room_id}/join")
async def join_room_endpoint(room_id: int, username: str = Query(...)) -> dict:
    """Join a room."""
    room = await rooms.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    joined = await rooms.join_room(room_id, username)
    return {"joined": joined, "room_id": room_id, "username": username}


@app.post("/rooms/{room_id}/leave")
async def leave_room_endpoint(room_id: int, username: str = Query(...)) -> dict:
    """Leave a room."""
    left = await rooms.leave_room(room_id, username)
    return {"left": left, "room_id": room_id, "username": username}


# ---- REST: Messages ----

@app.get("/rooms/{room_id}/messages", response_model=PaginatedMessages)
async def get_messages_endpoint(
    room_id: int, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
) -> PaginatedMessages:
    """Get paginated message history for a room."""
    return await messages.get_messages(room_id, limit=limit, offset=offset)


@app.get("/rooms/{room_id}/messages/search")
async def search_messages_endpoint(room_id: int, q: str = Query(..., min_length=1)) -> list:
    """Search messages by keyword."""
    results = await messages.search_messages(room_id, q)
    return [r.model_dump() for r in results]


# ---- REST: Presence ----

@app.get("/presence")
async def get_presence() -> dict:
    """Get all online users by room."""
    return presence.get_all_online()


@app.get("/rooms/{room_id}/presence")
async def get_room_presence(room_id: int) -> dict:
    """Get online users in a specific room."""
    return {"room_id": room_id, "online_users": presence.get_room_users(room_id)}


# ---- WebSocket ----

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, username: str = Query(...)) -> None:
    """WebSocket endpoint for real-time chat."""
    await manager.connect(websocket, username)
    logger.info("User %s connected via WebSocket", username)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "join_room":
                room_id = data["room_id"]
                manager.join_room(room_id, username)
                presence.user_joined(room_id, username)
                await rooms.join_room(room_id, username)
                await manager.broadcast_to_room(room_id, {
                    "type": "system",
                    "data": {"message": f"{username} joined the room", "username": username, "room_id": room_id},
                })

            elif msg_type == "leave_room":
                room_id = data["room_id"]
                manager.leave_room(room_id, username)
                presence.user_left(room_id, username)
                await rooms.leave_room(room_id, username)
                await manager.broadcast_to_room(room_id, {
                    "type": "system",
                    "data": {"message": f"{username} left the room", "username": username, "room_id": room_id},
                })

            elif msg_type == "send_message":
                room_id = data["room_id"]
                content = data["content"]
                msg = await messages.save_message(room_id, username, content)
                await manager.broadcast_to_room(room_id, {
                    "type": "message",
                    "data": msg.model_dump(),
                })

            elif msg_type == "typing":
                room_id = data["room_id"]
                is_typing = data.get("is_typing", True)
                await manager.broadcast_to_room(room_id, {
                    "type": "typing",
                    "data": {"username": username, "room_id": room_id, "is_typing": is_typing},
                }, exclude=username)

            elif msg_type == "dm":
                to_user = data["to_username"]
                content = data["content"]
                sent = await manager.send_to_user(to_user, {
                    "type": "dm",
                    "data": {"from": username, "content": content},
                })
                if not sent:
                    await websocket.send_json({
                        "type": "system",
                        "data": {"message": f"User {to_user} is not online"},
                    })

    except WebSocketDisconnect:
        logger.info("User %s disconnected", username)
    except Exception as e:
        logger.error("WebSocket error for %s: %s", username, e)
    finally:
        rooms_left = manager.disconnect(username)
        affected_rooms = presence.user_disconnected(username)
        for room_id in affected_rooms:
            await manager.broadcast_to_room(room_id, {
                "type": "system",
                "data": {"message": f"{username} went offline", "username": username, "room_id": room_id},
            })


if __name__ == "__main__":
    import uvicorn
    from src.config import HOST, PORT
    uvicorn.run("src.main:app", host=HOST, port=PORT, reload=True)
