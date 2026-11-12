"""Stub routes for the Telnet protocol module.

TODO (Roll 14): Replace these placeholder endpoints with real Telnet
server integration.  Follow the pattern in ``bootp_routes.py`` for
wiring :class:`PacketLogger` callbacks and managing a module-level
server instance.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from backend.models import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telnet", tags=["Telnet"])

_NOT_IMPL = ApiResponse(
    status="not_implemented",
    message="Telnet module not yet integrated",
)


# ===================================================================
# TODO (Roll 14): Implement the following endpoints
# ===================================================================


@router.post("/start-server", response_model=ApiResponse)
async def start_server() -> ApiResponse:
    """Start the Telnet server.

    TODO (Roll 14):
        - Import the Telnet server from ``protocols.telnet``
        - Wire :meth:`PacketLogger.get_callback_for_protocol('telnet')` as the
          packet callback.
        - Store the server instance at module level.
        - Update protocol status via the database.
    """
    return _NOT_IMPL


@router.post("/stop-server", response_model=ApiResponse)
async def stop_server() -> ApiResponse:
    """Stop the Telnet server.

    TODO (Roll 14):
        - Call ``stop()`` on the module-level server instance.
        - Update protocol status in the database.
    """
    return _NOT_IMPL


@router.get("/sessions", response_model=ApiResponse)
async def get_sessions() -> ApiResponse:
    """List active Telnet sessions.

    TODO (Roll 14):
        - Query the Telnet server for connected clients / sessions.
    """
    return _NOT_IMPL


@router.get("/logs", response_model=ApiResponse)
async def get_logs() -> ApiResponse:
    """Retrieve Telnet packet logs from the database.

    TODO (Roll 14):
        - Query ``PacketDatabase.get_packets(protocol='telnet')``.
    """
    return _NOT_IMPL
