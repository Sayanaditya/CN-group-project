"""Stub routes for the DNS protocol module.

TODO (Roll 11): Replace these placeholder endpoints with real DNS
server/client integration.  Follow the pattern in ``bootp_routes.py``
for wiring :class:`PacketLogger` callbacks and managing a module-level
server instance.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from backend.models import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dns", tags=["DNS"])

_NOT_IMPL = ApiResponse(
    status="not_implemented",
    message="DNS module not yet integrated",
)


# ===================================================================
# TODO (Roll 11): Implement the following endpoints
# ===================================================================


@router.post("/start-server", response_model=ApiResponse)
async def start_server() -> ApiResponse:
    """Start the DNS server.

    TODO (Roll 11):
        - Import the DNS server from ``protocols.dns``
        - Wire :meth:`PacketLogger.get_callback_for_protocol('dns')` as the
          packet callback.
        - Store the server instance at module level so it can be stopped.
        - Update protocol status via the database.
    """
    return _NOT_IMPL


@router.post("/stop-server", response_model=ApiResponse)
async def stop_server() -> ApiResponse:
    """Stop the DNS server.

    TODO (Roll 11):
        - Call ``stop()`` on the module-level server instance.
        - Update protocol status in the database.
    """
    return _NOT_IMPL


@router.post("/query", response_model=ApiResponse)
async def dns_query() -> ApiResponse:
    """Send a DNS query.

    TODO (Roll 11):
        - Accept query parameters (domain, record type).
        - Use the DNS client to resolve and return the result.
    """
    return _NOT_IMPL


@router.get("/zone", response_model=ApiResponse)
async def get_zone() -> ApiResponse:
    """Get the current DNS zone file contents.

    TODO (Roll 11):
        - Read and return the zone file from ``data/zone.txt``.
    """
    return _NOT_IMPL


@router.put("/zone", response_model=ApiResponse)
async def update_zone() -> ApiResponse:
    """Update the DNS zone file.

    TODO (Roll 11):
        - Accept new zone data and write it to ``data/zone.txt``.
        - Optionally reload the DNS server.
    """
    return _NOT_IMPL


@router.get("/logs", response_model=ApiResponse)
async def get_logs() -> ApiResponse:
    """Retrieve DNS packet logs from the database.

    TODO (Roll 11):
        - Query ``PacketDatabase.get_packets(protocol='dns')``.
    """
    return _NOT_IMPL
