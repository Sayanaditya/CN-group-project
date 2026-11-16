from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.models import ApiResponse
from logger.packet_logger import PacketLogger
from protocols.dns.client import DNSClient
from protocols.dns.service import DNSService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dns", tags=["DNS"])

ZONE_PATH = Path("data/zone.txt")
_dns_service: Optional[DNSService] = None


class DNSQueryRequest(BaseModel):
    domain: str
    type: str = "A"
    record_type: Optional[str] = None
    tcp: bool = False


class DNSZoneUpdate(BaseModel):
    zone: Optional[str] = None
    content: Optional[str] = None


def _detect_origin() -> str:
    if ZONE_PATH.exists():
        text = ZONE_PATH.read_text(encoding="utf-8")
        if "example.local" in text:
            return "example.local"
    return "example.test"


@router.post("/start-server", response_model=ApiResponse)
async def start_server() -> ApiResponse:
    global _dns_service
    if _dns_service is not None and any(t.is_alive() for t in _dns_service.threads):
        return ApiResponse(status="error", message="DNS server is already running.")

    pkt_logger = PacketLogger.get_instance()
    callback = pkt_logger.get_callback_for_protocol("dns")

    try:
        _dns_service = DNSService(
            zone_path=str(ZONE_PATH),
            origin=_detect_origin(),
            host="0.0.0.0",
            port=10053,
            upstream=("8.8.8.8", 53),
            on_packet_callback=callback,
        )
        info = _dns_service.start()
    except Exception as exc:
        _dns_service = None
        logger.exception("Failed to start DNS server")
        return ApiResponse(status="error", message=str(exc))

    if pkt_logger._db:
        await pkt_logger._db.update_protocol_status("dns", "running")

    return ApiResponse(status="success", message="DNS server started on 0.0.0.0:10053 (UDP + TCP).", data=info)


@router.post("/stop-server", response_model=ApiResponse)
async def stop_server() -> ApiResponse:
    global _dns_service
    if _dns_service is None:
        return ApiResponse(status="error", message="DNS server is not running.")

    _dns_service.stop()
    _dns_service = None

    db = PacketLogger.get_instance()._db
    if db:
        await db.update_protocol_status("dns", "stopped")

    return ApiResponse(status="success", message="DNS server stopped.")


@router.post("/query", response_model=ApiResponse)
async def dns_query(
    payload: Optional[DNSQueryRequest] = None,
    domain: Optional[str] = None,
    record_type: Optional[str] = None,
    type: Optional[str] = None,
) -> ApiResponse:
    q_domain = (payload.domain if payload else None) or domain
    q_type = (
        (payload.record_type or payload.type if payload else None)
        or record_type
        or type
        or "A"
    ).upper()
    use_tcp = payload.tcp if payload else False

    if not q_domain:
        return ApiResponse(status="error", message="Missing domain name.")

    port = _dns_service.port if _dns_service else 10053
    try:
        msg, elapsed_ms = DNSClient("127.0.0.1", port).query(q_domain, q_type, tcp=use_tcp)
    except Exception as exc:
        return ApiResponse(status="error", message=f"DNS query failed: {exc}")

    answers = [
        {"name": r.name, "type": r.rtype, "ttl": r.ttl, "value": r.value, "rdata": r.value}
        for r in msg.answers
    ]
    return ApiResponse(
        status="success",
        message=f"Resolved {q_domain} ({q_type}) in {elapsed_ms:.2f} ms.",
        data={
            "domain": q_domain,
            "type": q_type,
            "rcode": msg.rcode,
            "response_time_ms": round(elapsed_ms, 3),
            "answers": answers,
        },
    )


@router.get("/zone", response_model=ApiResponse)
async def get_zone() -> ApiResponse:
    if not ZONE_PATH.exists():
        return ApiResponse(status="error", message="Zone file not found.")
    return ApiResponse(status="success", message="Zone file loaded.", data=ZONE_PATH.read_text(encoding="utf-8"))


@router.put("/zone", response_model=ApiResponse)
async def update_zone(payload: DNSZoneUpdate) -> ApiResponse:
    text = payload.zone if payload.zone is not None else payload.content
    if text is None:
        return ApiResponse(status="error", message="No zone content provided.")

    ZONE_PATH.write_text(text, encoding="utf-8")
    if _dns_service is not None:
        _dns_service.reload_zone()
    return ApiResponse(status="success", message="Zone file saved and reloaded.")


@router.get("/logs", response_model=ApiResponse)
async def get_logs(limit: int = 100) -> ApiResponse:
    db = PacketLogger.get_instance()._db
    if db is None:
        return ApiResponse(status="error", message="Database not initialised.")
    packets = await db.get_packets(protocol="dns", limit=limit)
    return ApiResponse(status="success", message=f"{len(packets)} log(s) retrieved.", data=packets)
