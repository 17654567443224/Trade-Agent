"""WebSocket connection manager — broadcasts JSON events to all connected clients."""
import asyncio
import json
import logging
from typing import Any, Dict, Set

from fastapi import WebSocket

logger = logging.getLogger("api.ws_manager")


class ConnectionManager:
    def __init__(self) -> None:
        self._active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.add(ws)
        logger.info(f"[ws] client connected, total={len(self._active)}")

    def disconnect(self, ws: WebSocket) -> None:
        self._active.discard(ws)
        logger.info(f"[ws] client disconnected, total={len(self._active)}")

    async def send_to(self, ws: WebSocket, event_type: str, data: Any) -> None:
        """Send a typed JSON event to a single client."""
        payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=False, default=str)
        try:
            await ws.send_text(payload)
        except Exception:
            self._active.discard(ws)

    async def broadcast(self, event_type: str, data: Any) -> None:
        """Send a typed JSON event to every connected client."""
        payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=False, default=str)
        dead: list[WebSocket] = []
        for ws in list(self._active):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._active.discard(ws)


manager = ConnectionManager()
