"""Centralized packet logger with WebSocket callback bridge."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Optional

from logger.db import PacketDatabase

logger = logging.getLogger(__name__)


class PacketLogger:
    """Singleton packet logger that writes to the database and fans-out to
    registered WebSocket callbacks.

    Usage::

        pkt_logger = PacketLogger.get_instance()
        pkt_logger.set_database(db)
        pkt_logger.register_ws_callback(my_broadcast_fn)

    Protocols running in background threads should use
    :meth:`get_callback_for_protocol` to obtain a **sync** callable that
    safely schedules the async work on the event loop via
    :func:`asyncio.run_coroutine_threadsafe`.
    """

    _instance: Optional["PacketLogger"] = None

    def __init__(self) -> None:
        """Private constructor — use :meth:`get_instance` instead."""
        self._db: Optional[PacketDatabase] = None
        self._ws_callbacks: list[Callable[[dict], Coroutine[Any, Any, None]]] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @classmethod
    def get_instance(cls) -> "PacketLogger":
        """Return the singleton :class:`PacketLogger` instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_database(self, db: PacketDatabase) -> None:
        """Attach the database that packets will be persisted to.

        Args:
            db: An initialised :class:`PacketDatabase`.
        """
        self._db = db

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store a reference to the running event loop for thread-safe scheduling.

        Args:
            loop: The asyncio event loop used by the FastAPI application.
        """
        self._loop = loop

    # ------------------------------------------------------------------
    # WebSocket callback management
    # ------------------------------------------------------------------

    def register_ws_callback(
        self, callback: Callable[[dict], Coroutine[Any, Any, None]]
    ) -> None:
        """Register an async callback that will be invoked for every packet.

        Args:
            callback: An async function accepting a single ``dict`` argument.
        """
        if callback not in self._ws_callbacks:
            self._ws_callbacks.append(callback)
            logger.debug("Registered WS callback: %s", callback)

    def unregister_ws_callback(
        self, callback: Callable[[dict], Coroutine[Any, Any, None]]
    ) -> None:
        """Remove a previously registered async callback.

        Args:
            callback: The callback to remove.
        """
        try:
            self._ws_callbacks.remove(callback)
            logger.debug("Unregistered WS callback: %s", callback)
        except ValueError:
            logger.warning("Attempted to unregister unknown callback: %s", callback)

    # ------------------------------------------------------------------
    # Core logging
    # ------------------------------------------------------------------

    async def log_packet(self, packet_event: dict) -> None:
        """Persist a packet event to the database and notify all WS callbacks.

        Args:
            packet_event: A dictionary describing the captured packet.
        """
        # Store in database
        if self._db is not None:
            try:
                await self._db.insert_packet(packet_event)
            except Exception:
                logger.exception("Failed to insert packet into database")

        # Fan-out to WebSocket callbacks
        for cb in list(self._ws_callbacks):
            try:
                await cb(packet_event)
            except Exception:
                logger.exception("WebSocket callback %s failed", cb)

    # ------------------------------------------------------------------
    # Thread-safe bridge for sync protocol code
    # ------------------------------------------------------------------

    def get_callback_for_protocol(self, protocol: str) -> Callable[[dict], None]:
        """Return a **synchronous** callback suitable for protocol threads.

        The returned function schedules :meth:`log_packet` on the stored
        event loop using :func:`asyncio.run_coroutine_threadsafe`, making it
        safe to call from non-async code running in a background thread.

        Args:
            protocol: Protocol name injected into every packet event.

        Returns:
            A sync callable ``(packet_event: dict) -> None``.
        """

        def _sync_callback(packet_event: dict) -> None:
            packet_event.setdefault("protocol", protocol)
            loop = self._loop
            if loop is None:
                logger.error(
                    "Event loop not set on PacketLogger — cannot log packet for %s",
                    protocol,
                )
                return
            asyncio.run_coroutine_threadsafe(self.log_packet(packet_event), loop)

        return _sync_callback
