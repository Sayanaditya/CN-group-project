"""BOOTP packet builder and parser following RFC 951.

A BOOTP packet is EXACTLY 300 bytes with a fixed layout.  This module
provides the :class:`BOOTPPacket` dataclass that can serialise to / parse
from the wire format using :mod:`struct`, and convert to a plain dict for
JSON-based visualisation.

Packet layout (300 bytes total)::

    Offset  Size  Field
    ------  ----  -----
      0       1   op       – message opcode (1=request, 2=reply)
      1       1   htype    – hardware address type (1=Ethernet)
      2       1   hlen     – hardware address length (6 for MAC)
      3       1   hops     – relay hops
      4       4   xid      – transaction ID
      8       2   secs     – seconds elapsed
     10       2   flags    – flags (bit 15 = broadcast)
     12       4   ciaddr   – client IP address
     16       4   yiaddr   – 'your' (assigned) IP
     20       4   siaddr   – next-server IP
     24       4   giaddr   – relay-agent IP
     28      16   chaddr   – client hardware address (+ padding)
     44      64   sname    – server host name
    108     128   file     – boot file name
    236      64   vend     – vendor-specific / options area
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOOTP_PACKET_SIZE: int = 300
"""Fixed size of a BOOTP packet on the wire."""

BOOTREQUEST: int = 1
BOOTREPLY: int = 2

HTYPE_ETHERNET: int = 1
HLEN_ETHERNET: int = 6

# RFC 1048 magic cookie that begins the vendor/options area
MAGIC_COOKIE: bytes = bytes([99, 130, 83, 99])

# struct format for the fixed header (everything before vendor area)
#   B  B  B  B  – op, htype, hlen, hops
#   I            – xid  (network byte-order uint32)
#   H  H         – secs, flags
#   4s 4s 4s 4s  – ciaddr, yiaddr, siaddr, giaddr
#   16s          – chaddr
#   64s          – sname
#   128s         – file
_HEADER_FMT: str = "!BBBB I HH 4s4s4s4s 16s 64s 128s"
_HEADER_SIZE: int = struct.calcsize(_HEADER_FMT)  # 236 bytes

_VEND_SIZE: int = BOOTP_PACKET_SIZE - _HEADER_SIZE  # 64 bytes


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _mac_bytes_to_str(raw: bytes) -> str:
    """Convert the first 6 bytes of *raw* into a colon-separated MAC string.

    Args:
        raw: At least 6 bytes of hardware-address data.

    Returns:
        Human-readable MAC such as ``"aa:bb:cc:dd:ee:ff"``.
    """
    return ":".join(f"{b:02x}" for b in raw[:HLEN_ETHERNET])


def _mac_str_to_bytes(mac: str) -> bytes:
    """Convert a colon/dash-separated MAC string to 6 raw bytes.

    Args:
        mac: MAC address string (e.g. ``"aa:bb:cc:dd:ee:ff"``).

    Returns:
        6-byte representation of the MAC address.
    """
    mac = mac.replace("-", ":").lower()
    parts = mac.split(":")
    if len(parts) != 6:
        raise ValueError(f"Invalid MAC address: {mac!r}")
    return bytes(int(p, 16) for p in parts)


def _ip_bytes_to_str(raw: bytes) -> str:
    """Convert 4 raw bytes to a dotted-decimal IP string.

    Args:
        raw: Exactly 4 bytes representing an IPv4 address.

    Returns:
        Dotted-decimal string such as ``"192.168.1.1"``.
    """
    return socket.inet_ntoa(raw)


def _ip_str_to_bytes(ip: str) -> bytes:
    """Convert a dotted-decimal IP string to 4 raw bytes.

    Args:
        ip: IPv4 address string.

    Returns:
        4-byte network-order representation.
    """
    return socket.inet_aton(ip)


def hex_dump(data: bytes, width: int = 16) -> str:
    """Return a classic hex-dump string of *data*.

    Args:
        data: Raw bytes to dump.
        width: Number of bytes per line.

    Returns:
        Multi-line hex dump string.
    """
    lines: list[str] = []
    for offset in range(0, len(data), width):
        chunk = data[offset: offset + width]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{offset:04x}  {hex_part:<{width * 3}}  {ascii_part}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# BOOTPPacket dataclass
# ---------------------------------------------------------------------------

@dataclass
class BOOTPPacket:
    """Represents a single BOOTP packet (RFC 951).

    Provides serialisation (:meth:`to_bytes`), parsing
    (:meth:`from_bytes`), and JSON-friendly export (:meth:`to_dict`).

    Attributes:
        op: Message opcode – ``1`` for BOOTREQUEST, ``2`` for BOOTREPLY.
        htype: Hardware address type (``1`` = Ethernet).
        hlen: Hardware address length (``6`` for MAC).
        hops: Relay hop count.
        xid: Transaction ID (32-bit unsigned).
        secs: Seconds elapsed since client started trying.
        flags: Flags field (bit 15 = broadcast).
        ciaddr: Client IP address (dotted-decimal string).
        yiaddr: 'Your' (assigned) IP address.
        siaddr: Server IP address.
        giaddr: Gateway / relay-agent IP address.
        chaddr: Client hardware (MAC) address string.
        sname: Optional server hostname.
        file: Boot file name.
        vend: Raw vendor-specific area bytes.
    """

    op: int = BOOTREQUEST
    htype: int = HTYPE_ETHERNET
    hlen: int = HLEN_ETHERNET
    hops: int = 0
    xid: int = 0
    secs: int = 0
    flags: int = 0
    ciaddr: str = "0.0.0.0"
    yiaddr: str = "0.0.0.0"
    siaddr: str = "0.0.0.0"
    giaddr: str = "0.0.0.0"
    chaddr: str = "00:00:00:00:00:00"
    sname: str = ""
    file: str = ""
    vend: bytes = field(default_factory=lambda: MAGIC_COOKIE + b"\xff" + b"\x00" * 59)

    # ---- Serialisation ----------------------------------------------------

    def to_bytes(self) -> bytes:
        """Serialise this packet to exactly 300 bytes.

        Returns:
            A 300-byte :class:`bytes` object ready to send on the wire.
        """
        chaddr_raw = _mac_str_to_bytes(self.chaddr).ljust(16, b"\x00")

        sname_raw = self.sname.encode("ascii", errors="ignore")[:64].ljust(64, b"\x00")
        file_raw = self.file.encode("ascii", errors="ignore")[:128].ljust(128, b"\x00")

        header = struct.pack(
            _HEADER_FMT,
            self.op,
            self.htype,
            self.hlen,
            self.hops,
            self.xid,
            self.secs,
            self.flags,
            _ip_str_to_bytes(self.ciaddr),
            _ip_str_to_bytes(self.yiaddr),
            _ip_str_to_bytes(self.siaddr),
            _ip_str_to_bytes(self.giaddr),
            chaddr_raw,
            sname_raw,
            file_raw,
        )

        vend_padded = (self.vend or b"")[:_VEND_SIZE].ljust(_VEND_SIZE, b"\x00")
        packet = header + vend_padded
        assert len(packet) == BOOTP_PACKET_SIZE, f"Packet size mismatch: {len(packet)}"
        return packet

    # ---- Parsing ----------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes) -> BOOTPPacket:
        """Parse a raw 300-byte datagram into a :class:`BOOTPPacket`.

        Args:
            data: At least 300 bytes of raw packet data.

        Returns:
            Populated :class:`BOOTPPacket` instance.

        Raises:
            ValueError: If *data* is shorter than 300 bytes.
        """
        if len(data) < BOOTP_PACKET_SIZE:
            raise ValueError(
                f"BOOTP packet too short: {len(data)} bytes "
                f"(expected {BOOTP_PACKET_SIZE})"
            )

        fields = struct.unpack(_HEADER_FMT, data[:_HEADER_SIZE])
        (
            op, htype, hlen, hops,
            xid,
            secs, flags,
            ciaddr_raw, yiaddr_raw, siaddr_raw, giaddr_raw,
            chaddr_raw,
            sname_raw,
            file_raw,
        ) = fields

        vend_raw = data[_HEADER_SIZE: _HEADER_SIZE + _VEND_SIZE]

        return cls(
            op=op,
            htype=htype,
            hlen=hlen,
            hops=hops,
            xid=xid,
            secs=secs,
            flags=flags,
            ciaddr=_ip_bytes_to_str(ciaddr_raw),
            yiaddr=_ip_bytes_to_str(yiaddr_raw),
            siaddr=_ip_bytes_to_str(siaddr_raw),
            giaddr=_ip_bytes_to_str(giaddr_raw),
            chaddr=_mac_bytes_to_str(chaddr_raw),
            sname=sname_raw.rstrip(b"\x00").decode("ascii", errors="replace"),
            file=file_raw.rstrip(b"\x00").decode("ascii", errors="replace"),
            vend=vend_raw,
        )

    # ---- JSON export ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dictionary of all packet fields.

        Returns:
            A dictionary suitable for ``json.dumps`` or WebSocket streaming.
        """
        op_name = "BOOTREQUEST" if self.op == BOOTREQUEST else "BOOTREPLY"
        return {
            "op": self.op,
            "op_name": op_name,
            "htype": self.htype,
            "hlen": self.hlen,
            "hops": self.hops,
            "xid": f"0x{self.xid:08x}",
            "secs": self.secs,
            "flags": f"0x{self.flags:04x}",
            "ciaddr": self.ciaddr,
            "yiaddr": self.yiaddr,
            "siaddr": self.siaddr,
            "giaddr": self.giaddr,
            "chaddr": self.chaddr,
            "sname": self.sname,
            "file": self.file,
            "vend_hex": self.vend.hex(),
        }

    # ---- Pretty printing --------------------------------------------------

    def __str__(self) -> str:
        """Return a human-readable multi-line representation of the packet."""
        op_name = "BOOTREQUEST" if self.op == BOOTREQUEST else "BOOTREPLY"
        lines = [
            "╔══════════════════════════════════════════════╗",
            f"║  BOOTP {op_name:<39}║",
            "╠══════════════════════════════════════════════╣",
            f"║  op      : {self.op} ({op_name})",
            f"║  htype   : {self.htype}",
            f"║  hlen    : {self.hlen}",
            f"║  hops    : {self.hops}",
            f"║  xid     : 0x{self.xid:08x}",
            f"║  secs    : {self.secs}",
            f"║  flags   : 0x{self.flags:04x}",
            f"║  ciaddr  : {self.ciaddr}",
            f"║  yiaddr  : {self.yiaddr}",
            f"║  siaddr  : {self.siaddr}",
            f"║  giaddr  : {self.giaddr}",
            f"║  chaddr  : {self.chaddr}",
            f"║  sname   : {self.sname!r}",
            f"║  file    : {self.file!r}",
            f"║  vend    : {self.vend[:8].hex()}...",
            "╚══════════════════════════════════════════════╝",
        ]
        return "\n".join(lines)
