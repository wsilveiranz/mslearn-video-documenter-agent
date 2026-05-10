"""WebSocket endpoint for streaming pipeline progress updates."""

from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = structlog.get_logger()
ws_router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections for progress streaming."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, video_id: str) -> None:
        await websocket.accept()
        if video_id not in self._connections:
            self._connections[video_id] = []
        self._connections[video_id].append(websocket)
        logger.info("ws.connected", video_id=video_id)

    def disconnect(self, websocket: WebSocket, video_id: str) -> None:
        if video_id in self._connections:
            self._connections[video_id] = [
                ws for ws in self._connections[video_id] if ws != websocket
            ]
            if not self._connections[video_id]:
                del self._connections[video_id]
        logger.info("ws.disconnected", video_id=video_id)

    async def send_progress(
        self,
        video_id: str,
        stage: str,
        step: int,
        total_steps: int,
        detail: str = "",
    ) -> None:
        """Broadcast a step-based progress update to all connections watching a video.

        Sends to all clients concurrently with a 2s timeout per client.
        Never blocks the pipeline — failures are silently handled.
        """
        if video_id not in self._connections:
            return

        message = json.dumps({
            "type": "progress",
            "video_id": video_id,
            "stage": stage,
            "step": step,
            "total_steps": total_steps,
            "detail": detail,
        })

        async def _send(ws: WebSocket) -> WebSocket | None:
            try:
                await asyncio.wait_for(ws.send_text(message), timeout=2.0)
                return None
            except Exception:
                return ws

        results = await asyncio.gather(
            *(_send(ws) for ws in self._connections[video_id]),
        )

        for result in results:
            if result is not None:
                self.disconnect(result, video_id)


manager = ConnectionManager()


@ws_router.websocket("/ws/progress/{video_id}")
async def websocket_progress(websocket: WebSocket, video_id: str) -> None:
    """WebSocket endpoint for streaming progress of a video processing job."""
    await manager.connect(websocket, video_id)
    try:
        while True:
            # Keep connection alive; receive any client messages (e.g., cancel)
            data = await websocket.receive_text()
            logger.debug("ws.received", video_id=video_id, data=data)
    except WebSocketDisconnect:
        manager.disconnect(websocket, video_id)
