"""WebSocket endpoint for live push events."""
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from ws_manager import manager

router = APIRouter()


@router.websocket("/ops/{op_id}/ws")
async def websocket_endpoint(websocket: WebSocket, op_id: str):
    await manager.connect(websocket, op_id)
    try:
        while True:
            await websocket.receive_text()  # keeps connection alive; ignore client messages
    except WebSocketDisconnect:
        manager.disconnect(websocket, op_id)
