"""
websocket.py
────────────
WebSocket endpoint and ConnectionManager.

The ConnectionManager holds a set of active WebSocket connections and
broadcasts SpeakerEvent JSON to all of them.  A background task reads
from the broadcast queue (populated by the orchestrator) and calls
broadcast() in a continuous loop.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket, WebSocketDisconnect

from api.schemas import SpeakerEvent

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Thread-safe manager for active WebSocket clients."""

    def __init__(self) -> None:
        self._active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.add(ws)
        logger.info("Client connected. Total: %d", len(self._active))

    def disconnect(self, ws: WebSocket) -> None:
        self._active.discard(ws)
        logger.info("Client disconnected. Total: %d", len(self._active))

    async def broadcast(self, event: SpeakerEvent) -> None:
        """Send event JSON to every connected client."""
        if not self._active:
            return
        payload = event.model_dump_json()
        dead: list[WebSocket] = []
        for ws in list(self._active):
            try:
                await ws.send_text(payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def websocket_endpoint(
    websocket: WebSocket,
    broadcast_queue: asyncio.Queue,
) -> None:
    """
    Main WebSocket handler.  Accepts a client and keeps the connection
    alive until disconnect.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Just keep the connection alive; broadcasting is driven by
            # the background broadcaster task, not per-message events.
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def broadcaster_task(broadcast_queue: asyncio.Queue) -> None:
    """
    Background coroutine that drains the broadcast queue and fans out
    SpeakerEvents to all connected WebSocket clients.
    """
    while True:
        event: SpeakerEvent = await broadcast_queue.get()
        await manager.broadcast(event)
