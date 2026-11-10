"""BOOTP protocol configuration constants and defaults.

Defines non-privileged port numbers, IP pool ranges, static MAC-to-IP
mappings, and network parameter defaults used by both the BOOTP server
and client.
"""

# ---------------------------------------------------------------------------
# Port Configuration (non-privileged ports to avoid requiring root)
# ---------------------------------------------------------------------------
SERVER_PORT: int = 10067
"""UDP port the BOOTP server listens on (standard is 67)."""

CLIENT_PORT: int = 10068
"""UDP port the BOOTP client listens on (standard is 68)."""

# ---------------------------------------------------------------------------
# IP Address Pool
# ---------------------------------------------------------------------------
IP_POOL_START: str = "192.168.1.100"
"""First address in the dynamic allocation pool."""

IP_POOL_END: str = "192.168.1.200"
"""Last address (inclusive) in the dynamic allocation pool."""

# ---------------------------------------------------------------------------
# Static MAC → IP Mapping Table
# ---------------------------------------------------------------------------
STATIC_MAC_IP_MAP: dict[str, str] = {
    "aa:bb:cc:dd:ee:01": "192.168.1.10",
    "aa:bb:cc:dd:ee:02": "192.168.1.11",
    "aa:bb:cc:dd:ee:03": "192.168.1.12",
    "aa:bb:cc:dd:ee:04": "192.168.1.13",
    "aa:bb:cc:dd:ee:05": "192.168.1.14",
}
"""Pre-configured MAC-to-IP reservations that take priority over the pool."""

# ---------------------------------------------------------------------------
# Network Defaults
# ---------------------------------------------------------------------------
SERVER_IP: str = "192.168.1.1"
"""IP address the BOOTP server advertises as its own (siaddr)."""

GATEWAY_IP: str = "192.168.1.1"
"""Default gateway IP placed in the giaddr field of replies."""

SUBNET_MASK: str = "255.255.255.0"
"""Subnet mask returned in the vendor-specific area."""

# ---------------------------------------------------------------------------
# Boot File
# ---------------------------------------------------------------------------
BOOT_FILE_NAME: str = "pxelinux.0"
"""Default boot file name placed in the 'file' field of BOOTREPLY packets."""
