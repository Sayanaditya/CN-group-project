"""WebSocket manager for broadcasting live packet events to connected clients."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages a set of connected WebSocket clients and broadcasts messages.

    Designed to be used as a singleton. Register
    :meth:`broadcast` as a callback on :class:`PacketLogger` so that
    every captured packet is pushed to the frontend in real-time.
    """

    def __init__(self) -> None:
        """Initialise with an empty set of active connections."""
        self._active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket client.

        Args:
            websocket: The incoming :class:`WebSocket` connection.
        """
        await websocket.accept()
        self._active_connections.append(websocket)
        logger.info(
            "WebSocket client connected. Total: %d", len(self._active_connections)
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket client from the active set.

        Args:
            websocket: The disconnected :class:`WebSocket`.
        """
        try:
            self._active_connections.remove(websocket)
        except ValueError:
            pass
        logger.info(
            "WebSocket client disconnected. Total: %d", len(self._active_connections)
        )

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to every connected client.

        Disconnected or errored clients are silently removed.

        Args:
            message: Dictionary to JSON-serialise and send.
        """
        payload = json.dumps(message, default=str)
        stale: list[WebSocket] = []

        for ws in self._active_connections:
            try:
                await ws.send_text(payload)
            except Exception:
                logger.debug("Removing stale WebSocket connection.")
                stale.append(ws)

        for ws in stale:
            self.disconnect(ws)

    @property
    def client_count(self) -> int:
        """Return the number of currently connected WebSocket clients."""
        return len(self._active_connections)
