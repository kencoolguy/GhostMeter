"""WebSocket endpoint for real-time monitor dashboard."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.monitor_service import monitor_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Connected WebSocket clients
_clients: set[WebSocket] = set()

# Background broadcast task
_broadcast_task: asyncio.Task | None = None


async def _broadcast_loop() -> None:
    """Push monitor snapshot to all connected clients every 1 second."""
    while True:
        try:
            if _clients:
                snapshot = await monitor_service.get_snapshot()
                message = json.dumps(snapshot)
                disconnected: list[WebSocket] = []
                for ws in _clients:
                    try:
                        await ws.send_text(message)
                    except Exception:
                        disconnected.append(ws)
                for ws in disconnected:
                    _clients.discard(ws)
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Error in monitor broadcast loop")
            await asyncio.sleep(1.0)


def start_broadcast() -> None:
    """Start the background broadcast task."""
    global _broadcast_task
    if _broadcast_task is None or _broadcast_task.done():
        _broadcast_task = asyncio.create_task(
            _broadcast_loop(), name="monitor-broadcast",
        )
        logger.info("Monitor broadcast started")


async def stop_broadcast() -> None:
    """Stop the background broadcast task and close all client connections."""
    global _broadcast_task
    if _broadcast_task and not _broadcast_task.done():
        _broadcast_task.cancel()
        try:
            await _broadcast_task
        except asyncio.CancelledError:
            pass
    _broadcast_task = None

    for ws in list(_clients):
        try:
            await ws.close()
        except Exception:
            pass
    _clients.clear()
    logger.info("Monitor broadcast stopped")


@router.websocket("/ws/monitor")
async def monitor_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time device monitoring."""
    await websocket.accept()
    _clients.add(websocket)
    logger.info("Monitor client connected (total: %d)", len(_clients))

    try:
        # Send immediate snapshot on connect
        snapshot = await monitor_service.get_snapshot()
        await websocket.send_text(json.dumps(snapshot))

        # Keep connection alive — client doesn't send data, just receives
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("Monitor client disconnected unexpectedly")
    finally:
        _clients.discard(websocket)
        logger.info("Monitor client disconnected (total: %d)", len(_clients))
