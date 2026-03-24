"""WebSocket endpoint for real-time task progress notifications."""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.services.auth import decode_access_token
from app.services.task_manager import subscribe, unsubscribe

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(None)):
    """Authenticate via JWT token in query param, then stream task updates."""
    if not token:
        await websocket.close(code=4001, reason="Token required")
        return

    try:
        payload = decode_access_token(token)
        user_id = payload["sub"]
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()
    queue = subscribe(user_id)

    try:
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_json(msg)
            except asyncio.TimeoutError:
                # Keep-alive ping
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe(user_id, queue)
