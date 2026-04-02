from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

router = APIRouter()


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    broker = websocket.app.state.ui_events
    base_url = str(websocket.base_url)
    queue = await broker.add_client(websocket, base_url)
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(jsonable_encoder(payload))
    except WebSocketDisconnect:
        return
    finally:
        await broker.remove_client(queue)
