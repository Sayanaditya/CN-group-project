"""Pydantic models shared across the backend."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class PacketEvent(BaseModel):
    """Represents a single captured packet event."""

    protocol: str = Field(..., description="Protocol name (e.g. bootp, dns, telnet)")
    type: str = Field("", description="Packet sub-type (e.g. BOOTREQUEST, BOOTREPLY)")
    timestamp: str = Field(..., description="ISO-8601 timestamp")
    source_ip: str = Field("", description="Source IP address")
    source_port: Optional[int] = Field(None, description="Source port number")
    dest_ip: str = Field("", description="Destination IP address")
    dest_port: Optional[int] = Field(None, description="Destination port number")
    raw_hex: str = Field("", description="Raw packet bytes in hex")
    packet_json: str = Field("", description="JSON-encoded packet details")


class ProtocolStatus(BaseModel):
    """Current running state of a protocol module."""

    protocol: str = Field(..., description="Protocol name")
    status: str = Field("stopped", description="'running' or 'stopped'")


class BOOTPConfig(BaseModel):
    """Configuration for starting the BOOTP server."""

    server_ip: str = Field("192.168.1.1", description="Server IP address")
    gateway_ip: str = Field("192.168.1.1", description="Gateway IP address")
    pool_start: str = Field("192.168.1.100", description="IP pool range start")
    pool_end: str = Field("192.168.1.200", description="IP pool range end")


class ServerControl(BaseModel):
    """Generic server start/stop command."""

    action: str = Field(..., description="'start' or 'stop'")


class ApiResponse(BaseModel):
    """Generic API response wrapper."""

    status: str = Field(..., description="'success' or 'error'")
    message: str = Field("", description="Human-readable message")
    data: Optional[Any] = Field(None, description="Response payload")
