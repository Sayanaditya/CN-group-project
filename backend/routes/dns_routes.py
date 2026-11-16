"""FastAPI routes for the DNS protocol module (Roll 11)."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

from backend.models import ApiResponse
from logger.packet_logger import PacketLogger
from protocols.dns.service import DNSService
from protocols.dns.zone import Zone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dns", tags=["DNS"])

_SERVICE: DNSService | None = None
_ZONE_PATH = Path("data/zone.txt")
_ZONE_ORIGIN = "example.local"


@router.post("/start-server", response_model=ApiResponse)
async def start_server() -> ApiResponse:
    global _SERVICE
    if _SERVICE is not None and _SERVICE.threads and any(t.is_alive() for t in _SERVICE.threads):
        return ApiResponse(status="success", message="DNS server is already running.",
                           data={"host": _SERVICE.host, "port": _SERVICE.port})
    try:
        callback = PacketLogger.get_instance().get_callback_for_protocol("dns")
        _SERVICE = DNSService(
            zone_path=str(_ZONE_PATH), origin=_ZONE_ORIGIN,
            host="127.0.0.1", port=10053,
            upstream=("1.1.1.1", 53), on_packet_callback=callback,
        )
        result = _SERVICE.start()
        db = PacketLogger.get_instance()._db
        if db is not None:
            await db.update_protocol_status("dns", "running")
        return ApiResponse(status="success", message="DNS server started.", data=result)
    except Exception as exc:
        logger.exception("Failed to start DNS server")
        _SERVICE = None
        return ApiResponse(status="error", message=str(exc))


@router.post("/stop-server", response_model=ApiResponse)
async def stop_server() -> ApiResponse:
    global _SERVICE
    if _SERVICE is None:
        return ApiResponse(status="error", message="DNS server is not running.")
    try:
        result = _SERVICE.stop()
        db = PacketLogger.get_instance()._db
        if db is not None:
            await db.update_protocol_status("dns", "stopped")
        _SERVICE = None
        return ApiResponse(status="success", message="DNS server stopped.", data=result)
    except Exception as exc:
        logger.exception("Error stopping DNS server")
        return ApiResponse(status="error", message=str(exc))


@router.post("/query", response_model=ApiResponse)
async def dns_query(payload: dict) -> ApiResponse:
    domain = str(payload.get("domain", "")).strip()
    record_type = str(payload.get("type", payload.get("record_type", "A"))).upper()
    tcp = bool(payload.get("tcp", False))
    if not domain:
        return ApiResponse(status="error", message="A domain is required.")
    if _SERVICE is None:
        return ApiResponse(status="error", message="Start the DNS server before querying.")
    try:
        result = await run_in_threadpool(_SERVICE.query, domain, record_type, tcp)
        return ApiResponse(status="success", message="DNS query completed.", data=result)
    except Exception as exc:
        logger.exception("DNS query failed")
        return ApiResponse(status="error", message=str(exc))


@router.get("/zone", response_model=ApiResponse)
async def get_zone() -> ApiResponse:
    try:
        content = _ZONE_PATH.read_text(encoding="utf-8")
        zone = Zone.from_file(str(_ZONE_PATH), _ZONE_ORIGIN)
        records = [{"name": r.name, "type": r.rtype, "value": r.value, "ttl": r.ttl}
                   for r in zone.records]
        return ApiResponse(status="success", message="DNS zone loaded.",
                           data={"content": content, "records": records})
    except Exception as exc:
        return ApiResponse(status="error", message=str(exc))


@router.put("/zone", response_model=ApiResponse)
async def update_zone(payload: dict) -> ApiResponse:
    content = payload.get("content", payload.get("zone", payload.get("text")))
    if not isinstance(content, str) or not content.strip():
        return ApiResponse(status="error", message="Provide non-empty zone text in 'content'.")
    try:
        _ZONE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = _ZONE_PATH.with_suffix(".tmp")
        temp_path.write_text(content, encoding="utf-8")
        # Validate before replacing the active zone file.
        Zone.from_file(str(temp_path), _ZONE_ORIGIN)
        temp_path.replace(_ZONE_PATH)
        records = None
        if _SERVICE is not None:
            records = _SERVICE.reload_zone()
        return ApiResponse(status="success", message="DNS zone updated.",
                           data={"records": records})
    except Exception as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        logger.exception("DNS zone update failed")
        return ApiResponse(status="error", message=str(exc))


@router.get("/logs", response_model=ApiResponse)
async def get_logs(limit: int = Query(default=100, ge=1, le=1000)) -> ApiResponse:
    db = PacketLogger.get_instance()._db
    if db is None:
        return ApiResponse(status="error", message="Database not initialised.")
    packets = await db.get_packets(protocol="dns", limit=limit)
    return ApiResponse(status="success", message=f"{len(packets)} DNS log(s) retrieved.",
                       data=packets)
