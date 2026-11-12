"""BOOTP client implementation (RFC 951).

Provides :class:`BOOTPClient` which constructs BOOTREQUEST datagrams,
sends them to a BOOTP server over UDP, and waits for the corresponding
BOOTREPLY.  Like the server, it supports an ``on_packet_callback`` hook
for real-time visualisation.
"""

from __future__ import annotations

import logging
import os
import random
import socket
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from protocols.bootp.config import CLIENT_PORT, SERVER_PORT
from protocols.bootp.packet import (
    BOOTREPLY,
    BOOTREQUEST,
    BOOTPPacket,
    HLEN_ETHERNET,
    HTYPE_ETHERNET,
    MAGIC_COOKIE,
    hex_dump,
)

logger = logging.getLogger(__name__)

# Type alias
PacketCallback = Callable[[dict[str, Any]], None]


def _generate_fake_mac() -> str:
    """Generate a locally-administered unicast MAC address.

    The second nibble is set to ``2`` (locally administered, unicast)
    so the address won't clash with any real OUI.

    Returns:
        A colon-separated MAC string, e.g. ``"02:ab:cd:ef:01:23"``.
    """
    octets = [random.randint(0x00, 0xFF) for _ in range(6)]
    # Ensure locally administered + unicast bits
    octets[0] = (octets[0] & 0xFE) | 0x02
    return ":".join(f"{o:02x}" for o in octets)


def _get_system_mac() -> str | None:
    """Attempt to retrieve the system's real MAC address.

    Returns:
        Colon-separated MAC string, or ``None`` if detection fails.
    """
    try:
        mac_int = uuid.getnode()
        # uuid.getnode returns a random if it can't find a real one;
        # the 8th bit of the first octet is set in that case.
        if (mac_int >> 40) & 0x01:
            return None
        mac_hex = f"{mac_int:012x}"
        return ":".join(mac_hex[i : i + 2] for i in range(0, 12, 2))
    except Exception:
        return None


class BOOTPClient:
    """A BOOTP client that sends requests and awaits server replies.

    Args:
        server_address: Hostname or IP of the BOOTP server.
        server_port: UDP port the server listens on.
        client_port: Local UDP port the client binds to for receiving
            the reply.
        timeout: Seconds to wait for a reply before giving up.
        on_packet_callback: Optional callable invoked with a packet-event
            dict whenever a request is sent or a reply is received.

    Example::

        client = BOOTPClient()
        reply = client.send_request(mac_address="aa:bb:cc:dd:ee:01")
        print(reply)
    """

    def __init__(
        self,
        server_address: str = "127.0.0.1",
        server_port: int = SERVER_PORT,
        client_port: int = CLIENT_PORT,
        timeout: float = 5.0,
        on_packet_callback: PacketCallback | None = None,
    ) -> None:
        """Initialise the BOOTP client."""
        self._server_address = server_address
        self._server_port = server_port
        self._client_port = client_port
        self._timeout = timeout
        self._on_packet_callback = on_packet_callback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_request(
        self,
        mac_address: str | None = None,
    ) -> BOOTPPacket | None:
        """Build and send a BOOTREQUEST, then wait for the BOOTREPLY.

        Args:
            mac_address: Client MAC to embed in the request.  If ``None``,
                the method first tries the system MAC, then falls back to
                a randomly generated locally-administered address.

        Returns:
            The parsed :class:`BOOTPPacket` reply from the server, or
            ``None`` if the request timed out.
        """
        # Resolve MAC address
        if mac_address is None:
            mac_address = _get_system_mac() or _generate_fake_mac()
            logger.debug("Using MAC address: %s", mac_address)
        mac_address = mac_address.lower()

        # Generate a random 32-bit transaction ID
        xid: int = random.randint(0, 0xFFFFFFFF)

        # Build vendor area with magic cookie
        vend = bytearray(64)
        vend[0:4] = MAGIC_COOKIE
        vend[4] = 0xFF  # End option

        request = BOOTPPacket(
            op=BOOTREQUEST,
            htype=HTYPE_ETHERNET,
            hlen=HLEN_ETHERNET,
            hops=0,
            xid=xid,
            secs=0,
            flags=0x8000,  # broadcast flag
            ciaddr="0.0.0.0",
            yiaddr="0.0.0.0",
            siaddr="0.0.0.0",
            giaddr="0.0.0.0",
            chaddr=mac_address,
            sname="",
            file="",
            vend=bytes(vend),
        )

        request_bytes = request.to_bytes()

        # Create the UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Bind to a specific port so the server reply comes back here
            sock.bind(("0.0.0.0", self._client_port))
            sock.settimeout(self._timeout)

            dest = (self._server_address, self._server_port)
            sock.sendto(request_bytes, dest)

            logger.info(
                "Sent BOOTREQUEST (xid=0x%08x, MAC=%s) → %s",
                xid,
                mac_address,
                dest,
            )

            # Fire callback for the outgoing request
            self._fire_callback(
                packet=request,
                pkt_type="BOOTREQUEST",
                source={"ip": "0.0.0.0", "port": self._client_port},
                destination={"ip": self._server_address, "port": self._server_port},
                raw_data=request_bytes,
            )

            # Wait for the reply
            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                except socket.timeout:
                    logger.warning(
                        "Timeout waiting for BOOTREPLY (xid=0x%08x)", xid
                    )
                    return None

                reply = BOOTPPacket.from_bytes(data)

                # Verify it's a reply for *our* transaction
                if reply.op != BOOTREPLY:
                    logger.debug("Ignoring non-BOOTREPLY packet")
                    continue
                if reply.xid != xid:
                    logger.debug(
                        "Ignoring reply with mismatched xid "
                        "(expected 0x%08x, got 0x%08x)",
                        xid,
                        reply.xid,
                    )
                    continue

                logger.info(
                    "Received BOOTREPLY: yiaddr=%s from %s",
                    reply.yiaddr,
                    addr,
                )

                # Fire callback for the incoming reply
                self._fire_callback(
                    packet=reply,
                    pkt_type="BOOTREPLY",
                    source={"ip": addr[0], "port": addr[1]},
                    destination={"ip": "0.0.0.0", "port": self._client_port},
                    raw_data=data,
                )

                return reply

        finally:
            sock.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fire_callback(
        self,
        packet: BOOTPPacket,
        pkt_type: str,
        source: dict[str, Any],
        destination: dict[str, Any],
        raw_data: bytes,
    ) -> None:
        """Invoke the registered packet callback, if any.

        Args:
            packet: The :class:`BOOTPPacket` being sent or received.
            pkt_type: ``"BOOTREQUEST"`` or ``"BOOTREPLY"``.
            source: ``{"ip": …, "port": …}`` of the sender.
            destination: ``{"ip": …, "port": …}`` of the receiver.
            raw_data: The raw bytes for hex-dump display.
        """
        if self._on_packet_callback is None:
            return

        event: dict[str, Any] = {
            "protocol": "BOOTP",
            "type": pkt_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "destination": destination,
            "packet": packet.to_dict(),
            "raw_hex": hex_dump(raw_data),
        }

        try:
            self._on_packet_callback(event)
        except Exception:
            logger.exception("Error in packet callback")


# -----------------------------------------------------------------------
# Standalone test
# -----------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    import sys

    mac = sys.argv[1] if len(sys.argv) > 1 else None

    def _demo_callback(event: dict[str, Any]) -> None:
        """Print packet events to stdout."""
        print(f"\n[CALLBACK] {event['type']} @ {event['timestamp']}")
        print(f"  src  = {event['source']}")
        print(f"  dst  = {event['destination']}")
        print(f"  xid  = {event['packet']['xid']}")
        print(f"  yiaddr = {event['packet']['yiaddr']}")

    client = BOOTPClient(on_packet_callback=_demo_callback)
    print(f"Sending BOOTREQUEST to 127.0.0.1:{SERVER_PORT} ...")

    reply = client.send_request(mac_address=mac)

    if reply is not None:
        print("\n=== BOOTREPLY received ===")
        print(reply)
    else:
        print("\n⚠  No reply received (timeout).")
