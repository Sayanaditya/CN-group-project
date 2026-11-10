"""FastAPI routes for the BOOTP protocol module."""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.models import ApiResponse, BOOTPConfig
from logger.packet_logger import PacketLogger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bootp", tags=["BOOTP"])

# ---------------------------------------------------------------------------
# Module-level server instance — set when the server is started.
# ---------------------------------------------------------------------------
_bootp_server = None
_bootp_server_task = None  # asyncio.Task or threading.Thread reference


def _load_pool_config(path: str = "data/bootp_pool.json") -> dict:
    """Load the BOOTP IP-pool configuration from disk.

    Args:
        path: Path to the JSON config file.

    Returns:
        Parsed configuration dictionary.
    """
    try:
        with open(path, "r") as fh:
            return json.load(fh)
    except FileNotFoundError:
        logger.warning("Pool config not found at %s — using defaults.", path)
        return {
            "server_ip": "192.168.1.1",
            "gateway_ip": "192.168.1.1",
            "subnet_mask": "255.255.255.0",
            "pool_start": "192.168.1.100",
            "pool_end": "192.168.1.200",
        }


# ===================================================================
# Routes
# ===================================================================


@router.post("/start-server", response_model=ApiResponse)
async def start_server(config: Optional[BOOTPConfig] = None) -> ApiResponse:
    """Start the BOOTP server.

    Imports the protocol implementation from ``protocols.bootp``, wires the
    :class:`PacketLogger` callback, and launches the server.

    Args:
        config: Optional custom pool configuration.

    Returns:
        An :class:`ApiResponse` indicating success or failure.
    """
    global _bootp_server, _bootp_server_task

    if _bootp_server is not None:
        return ApiResponse(status="error", message="BOOTP server is already running.")

    try:
        from protocols.bootp.server import BOOTPServer  # type: ignore[import-untyped]
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail=f"BOOTP protocol module not found: {exc}",
        )

    pool_cfg = _load_pool_config()
    if config:
        pool_cfg.update(
            {
                "server_ip": config.server_ip,
                "gateway_ip": config.gateway_ip,
                "pool_start": config.pool_start,
                "pool_end": config.pool_end,
            }
        )

    pkt_logger = PacketLogger.get_instance()
    callback = pkt_logger.get_callback_for_protocol("bootp")

    try:
        _bootp_server = BOOTPServer(
            server_ip=pool_cfg.get("server_ip", "192.168.1.1"),
            gateway_ip=pool_cfg.get("gateway_ip", "192.168.1.1"),
            ip_pool_start=pool_cfg.get("pool_start", "192.168.1.100"),
            ip_pool_end=pool_cfg.get("pool_end", "192.168.1.200"),
            static_map=pool_cfg.get("static_mappings"),
            on_packet_callback=callback,
        )
        _bootp_server.start()
    except Exception as exc:
        _bootp_server = None
        logger.exception("Failed to start BOOTP server")
        return ApiResponse(status="error", message=str(exc))

    # Update protocol status in the database
    db = pkt_logger._db
    if db:
        await db.update_protocol_status("bootp", "running")

    logger.info("BOOTP server started.")
    return ApiResponse(status="success", message="BOOTP server started.", data=pool_cfg)


@router.post("/stop-server", response_model=ApiResponse)
async def stop_server() -> ApiResponse:
    """Stop the running BOOTP server.

    Returns:
        An :class:`ApiResponse` indicating success or failure.
    """
    global _bootp_server

    if _bootp_server is None:
        return ApiResponse(status="error", message="BOOTP server is not running.")

    try:
        _bootp_server.stop()
    except Exception as exc:
        logger.exception("Error stopping BOOTP server")
        return ApiResponse(status="error", message=str(exc))
    finally:
        _bootp_server = None

    pkt_logger = PacketLogger.get_instance()
    db = pkt_logger._db
    if db:
        await db.update_protocol_status("bootp", "stopped")

    logger.info("BOOTP server stopped.")
    return ApiResponse(status="success", message="BOOTP server stopped.")


@router.post("/send-request", response_model=ApiResponse)
async def send_request(mac_address: Optional[str] = None) -> ApiResponse:
    """Trigger a BOOTREQUEST from the built-in client.

    Args:
        mac_address: Optional MAC address to include in the request.

    Returns:
        An :class:`ApiResponse` with the request result.
    """
    try:
        from protocols.bootp.client import BOOTPClient  # type: ignore[import-untyped]
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail=f"BOOTP client module not found: {exc}",
        )

    pkt_logger = PacketLogger.get_instance()
    callback = pkt_logger.get_callback_for_protocol("bootp")

    try:
        client = BOOTPClient(on_packet_callback=callback)
        result = client.send_request(mac_address=mac_address)
    except Exception as exc:
        logger.exception("BOOTP request failed")
        return ApiResponse(status="error", message=str(exc))

    if result is None:
        return ApiResponse(status="error", message="No BOOTREPLY received (timeout).")

    return ApiResponse(
        status="success",
        message="BOOTREPLY received.",
        data=result.to_dict(),
    )


@router.get("/pool", response_model=ApiResponse)
async def get_pool() -> ApiResponse:
    """Return the current IP-pool configuration.

    Returns:
        An :class:`ApiResponse` containing the pool config.
    """
    pool_cfg = _load_pool_config()
    return ApiResponse(status="success", message="Pool configuration loaded.", data=pool_cfg)


@router.get("/allocations", response_model=ApiResponse)
async def get_allocations() -> ApiResponse:
    """Return current MAC → IP allocations from the running server.

    Returns:
        An :class:`ApiResponse` with the allocation table.
    """
    if _bootp_server is None:
        return ApiResponse(
            status="error",
            message="BOOTP server is not running.",
            data={},
        )

    try:
        allocations = _bootp_server.get_allocations()
    except AttributeError:
        allocations = {}

    return ApiResponse(
        status="success",
        message="Current allocations.",
        data=allocations,
    )


@router.get("/logs", response_model=ApiResponse)
async def get_logs(limit: int = 100) -> ApiResponse:
    """Retrieve BOOTP packet logs from the database.

    Args:
        limit: Maximum number of log entries to return.

    Returns:
        An :class:`ApiResponse` containing the packet logs.
    """
    pkt_logger = PacketLogger.get_instance()
    db = pkt_logger._db
    if db is None:
        return ApiResponse(status="error", message="Database not initialised.")

    packets = await db.get_packets(protocol="bootp", limit=limit)
    return ApiResponse(status="success", message=f"{len(packets)} log(s) retrieved.", data=packets)
