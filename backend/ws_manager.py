"""WebSocket connection manager for live push events."""
import asyncio
from typing import Dict, List

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, op_id: str) -> None:
        await websocket.accept()
        self._connections.setdefault(op_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, op_id: str) -> None:
        sockets = self._connections.get(op_id, [])
        if websocket in sockets:
            sockets.remove(websocket)

    async def broadcast(self, op_id: str, event: dict) -> None:
        sockets = list(self._connections.get(op_id, []))
        dead = []
        for ws in sockets:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, op_id)


manager = ConnectionManager()


def broadcast_sync(op_id: str, event: dict) -> None:
    """Fire-and-forget broadcast from sync route handlers."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(manager.broadcast(op_id, event))
    except RuntimeError:
        pass  # no event loop — test environment
