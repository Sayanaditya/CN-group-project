"""BOOTP (Bootstrap Protocol) implementation following RFC 951.

This package provides a complete BOOTP client and server implementation
with packet parsing/building, configurable IP pools, and event callbacks
for real-time monitoring via WebSocket streaming.
"""

from protocols.bootp.packet import BOOTPPacket
from protocols.bootp.server import BOOTPServer
from protocols.bootp.client import BOOTPClient
from protocols.bootp.config import (
    SERVER_PORT,
    CLIENT_PORT,
    IP_POOL_START,
    IP_POOL_END,
    STATIC_MAC_IP_MAP,
    SERVER_IP,
    GATEWAY_IP,
    SUBNET_MASK,
    BOOT_FILE_NAME,
)

__all__ = [
    "BOOTPPacket",
    "BOOTPServer",
    "BOOTPClient",
    "SERVER_PORT",
    "CLIENT_PORT",
    "IP_POOL_START",
    "IP_POOL_END",
    "STATIC_MAC_IP_MAP",
    "SERVER_IP",
    "GATEWAY_IP",
    "SUBNET_MASK",
    "BOOT_FILE_NAME",
]
