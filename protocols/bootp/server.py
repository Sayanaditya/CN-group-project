"""BOOTP server implementation (RFC 951).

Provides :class:`BOOTPServer` which listens for BOOTREQUEST datagrams on a
configurable UDP port, assigns IP addresses from a static mapping table or
dynamic pool, and replies with BOOTREPLY packets.  The server runs in its
own daemon thread and exposes a callback hook so that every packet event can
be streamed to a web-based visualiser in real time.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from protocols.bootp.config import (
    BOOT_FILE_NAME,
    CLIENT_PORT,
    GATEWAY_IP,
    IP_POOL_END,
    IP_POOL_START,
    SERVER_IP,
    SERVER_PORT,
    STATIC_MAC_IP_MAP,
)
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

# Type alias for the event callback
PacketCallback = Callable[[dict[str, Any]], None]


class BOOTPServer:
    """A threaded UDP BOOTP server with dynamic IP pool management.

    Args:
        server_ip: IP address the server advertises as its own (``siaddr``).
        gateway_ip: Gateway address placed in ``giaddr`` of replies.
        listen_port: UDP port to bind on.
        client_port: Destination port when sending replies.
        ip_pool_start: First address of the dynamic pool.
        ip_pool_end: Last address (inclusive) of the dynamic pool.
        static_map: Pre-configured MAC → IP reservations.
        boot_file: Default boot filename for the ``file`` field.
        on_packet_callback: Optional callable invoked with a packet-event
            dict every time a request is received or a reply is sent.

    Example::

        server = BOOTPServer()
        server.start()
        # … later …
        server.stop()
    """

    def __init__(
        self,
        server_ip: str = SERVER_IP,
        gateway_ip: str = GATEWAY_IP,
        listen_port: int = SERVER_PORT,
        client_port: int = CLIENT_PORT,
        ip_pool_start: str = IP_POOL_START,
        ip_pool_end: str = IP_POOL_END,
        static_map: dict[str, str] | None = None,
        boot_file: str = BOOT_FILE_NAME,
        on_packet_callback: PacketCallback | None = None,
    ) -> None:
        """Initialise the BOOTP server with the given configuration."""
        self._server_ip = server_ip
        self._gateway_ip = gateway_ip
        self._listen_port = listen_port
        self._client_port = client_port
        self._boot_file = boot_file
        self._on_packet_callback = on_packet_callback

        # Static reservations (normalise keys to lower-case)
        self._static_map: dict[str, str] = {
            k.lower(): v for k, v in (static_map or STATIC_MAC_IP_MAP).items()
        }

        # Build the dynamic IP pool as a set of available addresses
        self._pool_lock = threading.Lock()
        pool_start = ipaddress.IPv4Address(ip_pool_start)
        pool_end = ipaddress.IPv4Address(ip_pool_end)
        self._all_pool_ips: list[str] = [
            str(ipaddress.IPv4Address(addr))
            for addr in range(int(pool_start), int(pool_end) + 1)
        ]
        self._available_ips: set[str] = set(self._all_pool_ips)

        # Allocation table: MAC (lower) → assigned IP
        self._allocations: dict[str, str] = {}

        # Thread / socket management
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the server in a background daemon thread.

        Raises:
            RuntimeError: If the server is already running.
        """
        if self._running.is_set():
            raise RuntimeError("BOOTP server is already running")

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.settimeout(1.0)  # allows periodic check of _running flag
        self._sock.bind(("0.0.0.0", self._listen_port))

        self._running.set()
        self._thread = threading.Thread(
            target=self._serve_forever,
            name="bootp-server",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "BOOTP server started on UDP port %d (server_ip=%s)",
            self._listen_port,
            self._server_ip,
        )

    def stop(self) -> None:
        """Gracefully stop the server and release the socket."""
        if not self._running.is_set():
            logger.warning("BOOTP server is not running")
            return

        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        logger.info("BOOTP server stopped")

    def is_running(self) -> bool:
        """Return ``True`` if the server thread is active."""
        return self._running.is_set()

    def get_pool_status(self) -> dict[str, Any]:
        """Return current pool utilisation statistics.

        Returns:
            Dictionary with keys ``total``, ``available``, ``allocated``.
        """
        with self._pool_lock:
            return {
                "total": len(self._all_pool_ips),
                "available": len(self._available_ips),
                "allocated": len(self._allocations),
            }

    def get_allocations(self) -> dict[str, str]:
        """Return a copy of the current MAC → IP allocation table.

        Returns:
            Dictionary mapping MAC address strings to assigned IP strings.
        """
        with self._pool_lock:
            return dict(self._allocations)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _serve_forever(self) -> None:
        """Main receive loop executed inside the server thread."""
        logger.debug("Server thread entering receive loop")
        while self._running.is_set():
            try:
                data, addr = self._sock.recvfrom(1024)  # type: ignore[union-attr]
            except socket.timeout:
                continue
            except OSError:
                if self._running.is_set():
                    logger.exception("Socket error in server loop")
                break

            logger.debug("Received %d bytes from %s", len(data), addr)
            try:
                self._handle_packet(data, addr)
            except Exception:
                logger.exception("Error handling packet from %s", addr)

    def _handle_packet(
        self,
        data: bytes,
        client_addr: tuple[str, int],
    ) -> None:
        """Parse an incoming datagram and respond if it's a BOOTREQUEST.

        Args:
            data: Raw received bytes.
            client_addr: ``(ip, port)`` tuple of the sender.
        """
        request = BOOTPPacket.from_bytes(data)

        if request.op != BOOTREQUEST:
            logger.debug("Ignoring non-BOOTREQUEST packet (op=%d)", request.op)
            return

        logger.info(
            "BOOTREQUEST from MAC %s (xid=0x%08x)",
            request.chaddr,
            request.xid,
        )

        # Fire callback for the incoming request
        self._fire_callback(
            packet=request,
            pkt_type="BOOTREQUEST",
            source={"ip": client_addr[0], "port": client_addr[1]},
            destination={"ip": "0.0.0.0", "port": self._listen_port},
            raw_data=data,
        )

        # Allocate an IP for this client
        assigned_ip = self._allocate_ip(request.chaddr)
        if assigned_ip is None:
            logger.warning("IP pool exhausted – cannot serve %s", request.chaddr)
            return

        # Build vendor area with magic cookie + subnet-mask option
        vend = bytearray(64)
        vend[0:4] = MAGIC_COOKIE
        # Option 1: Subnet Mask (tag=1, len=4, mask bytes)
        vend[4] = 1
        vend[5] = 4
        vend[6:10] = socket.inet_aton("255.255.255.0")
        # End option
        vend[10] = 0xFF

        reply = BOOTPPacket(
            op=BOOTREPLY,
            htype=HTYPE_ETHERNET,
            hlen=HLEN_ETHERNET,
            hops=0,
            xid=request.xid,
            secs=0,
            flags=request.flags,
            ciaddr=request.ciaddr,
            yiaddr=assigned_ip,
            siaddr=self._server_ip,
            giaddr=self._gateway_ip,
            chaddr=request.chaddr,
            sname="",
            file=self._boot_file,
            vend=bytes(vend),
        )

        reply_bytes = reply.to_bytes()

        # Determine reply destination: if client had an address, reply
        # unicast; otherwise send to the address we received from.
        dest_ip = client_addr[0] if client_addr[0] != "0.0.0.0" else "255.255.255.255"
        dest_port = client_addr[1]
        dest = (dest_ip, dest_port)

        self._sock.sendto(reply_bytes, dest)  # type: ignore[union-attr]

        logger.info(
            "BOOTREPLY → %s  assigned yiaddr=%s for MAC %s",
            dest,
            assigned_ip,
            request.chaddr,
        )

        # Fire callback for the outgoing reply
        self._fire_callback(
            packet=reply,
            pkt_type="BOOTREPLY",
            source={"ip": self._server_ip, "port": self._listen_port},
            destination={"ip": dest_ip, "port": dest_port},
            raw_data=reply_bytes,
        )

    def _allocate_ip(self, mac: str) -> str | None:
        """Allocate an IP for the given MAC address.

        Checks the static table first; falls back to the dynamic pool.

        Args:
            mac: Client MAC address string (colon-separated, lower-case).

        Returns:
            The allocated IP address string, or ``None`` if the pool is
            exhausted.
        """
        mac_lower = mac.lower()

        with self._pool_lock:
            # Already allocated in a previous exchange?
            if mac_lower in self._allocations:
                return self._allocations[mac_lower]

            # Check the static mapping table
            if mac_lower in self._static_map:
                ip = self._static_map[mac_lower]
                self._allocations[mac_lower] = ip
                # Remove from dynamic pool if it happens to overlap
                self._available_ips.discard(ip)
                logger.debug("Static allocation: %s → %s", mac_lower, ip)
                return ip

            # Dynamic allocation from the pool
            if not self._available_ips:
                return None
            ip = self._available_ips.pop()
            self._allocations[mac_lower] = ip
            logger.debug("Dynamic allocation: %s → %s", mac_lower, ip)
            return ip

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
            packet: The parsed :class:`BOOTPPacket`.
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

    def _demo_callback(event: dict[str, Any]) -> None:
        """Print packet events to stdout."""
        print(f"\n[CALLBACK] {event['type']} @ {event['timestamp']}")
        print(f"  src  = {event['source']}")
        print(f"  dst  = {event['destination']}")
        print(f"  xid  = {event['packet']['xid']}")
        print(f"  yiaddr = {event['packet']['yiaddr']}")

    server = BOOTPServer(on_packet_callback=_demo_callback)
    server.start()

    print(f"\nBOOTP server running on port {SERVER_PORT}.  Press Ctrl+C to stop.\n")
    try:
        while server.is_running():
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        print("\nPool status:", server.get_pool_status())
        print("Allocations:", server.get_allocations())
