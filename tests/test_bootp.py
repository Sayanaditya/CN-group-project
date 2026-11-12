"""Unit and integration tests for the BOOTP protocol module."""

import time
import unittest

from protocols.bootp.packet import (
    BOOTREPLY,
    BOOTREQUEST,
    BOOTP_PACKET_SIZE,
    BOOTPPacket,
    hex_dump,
)
from protocols.bootp.server import BOOTPServer
from protocols.bootp.client import BOOTPClient
from protocols.bootp.config import STATIC_MAC_IP_MAP


class TestBOOTPPacket(unittest.TestCase):
    """Tests for the BOOTPPacket dataclass."""

    def test_packet_size_is_300_bytes(self):
        """A default packet must serialise to exactly 300 bytes."""
        pkt = BOOTPPacket()
        raw = pkt.to_bytes()
        self.assertEqual(len(raw), BOOTP_PACKET_SIZE)

    def test_round_trip_preserves_fields(self):
        """Encoding then decoding should preserve every field."""
        pkt = BOOTPPacket(
            op=BOOTREQUEST,
            xid=0xCAFEBABE,
            flags=0x8000,
            chaddr="aa:bb:cc:dd:ee:ff",
            ciaddr="10.0.0.1",
            yiaddr="10.0.0.2",
            siaddr="10.0.0.3",
            giaddr="10.0.0.4",
            sname="testserver",
            file="pxelinux.0",
        )
        raw = pkt.to_bytes()
        pkt2 = BOOTPPacket.from_bytes(raw)

        self.assertEqual(pkt2.op, BOOTREQUEST)
        self.assertEqual(pkt2.xid, 0xCAFEBABE)
        self.assertEqual(pkt2.flags, 0x8000)
        self.assertEqual(pkt2.chaddr, "aa:bb:cc:dd:ee:ff")
        self.assertEqual(pkt2.ciaddr, "10.0.0.1")
        self.assertEqual(pkt2.yiaddr, "10.0.0.2")
        self.assertEqual(pkt2.siaddr, "10.0.0.3")
        self.assertEqual(pkt2.giaddr, "10.0.0.4")
        self.assertEqual(pkt2.sname, "testserver")
        self.assertEqual(pkt2.file, "pxelinux.0")

    def test_to_dict_returns_serializable(self):
        """to_dict() must return a JSON-serializable dictionary."""
        pkt = BOOTPPacket(op=BOOTREPLY, xid=0x12345678, chaddr="11:22:33:44:55:66")
        d = pkt.to_dict()
        self.assertEqual(d["op_name"], "BOOTREPLY")
        self.assertEqual(d["xid"], "0x12345678")
        self.assertEqual(d["chaddr"], "11:22:33:44:55:66")

    def test_short_packet_raises_error(self):
        """from_bytes must reject packets shorter than 300 bytes."""
        with self.assertRaises(ValueError):
            BOOTPPacket.from_bytes(b"\x00" * 100)

    def test_hex_dump_output(self):
        """hex_dump should return a multi-line string."""
        data = bytes(range(32))
        dump = hex_dump(data)
        self.assertIn("0000", dump)
        self.assertIn("0010", dump)


class TestBOOTPServerClient(unittest.TestCase):
    """Integration tests for BOOTP server + client."""

    @classmethod
    def setUpClass(cls):
        """Start the BOOTP server before all tests."""
        cls.events = []
        cls.server = BOOTPServer(
            on_packet_callback=lambda e: cls.events.append(e)
        )
        cls.server.start()
        time.sleep(0.3)  # Give server thread time to bind

    @classmethod
    def tearDownClass(cls):
        """Stop the BOOTP server after all tests."""
        cls.server.stop()

    def test_static_mac_assignment(self):
        """A MAC in the static table should get its reserved IP."""
        client = BOOTPClient()
        reply = client.send_request(mac_address="aa:bb:cc:dd:ee:01")
        self.assertIsNotNone(reply)
        self.assertEqual(reply.yiaddr, "192.168.1.10")

    def test_dynamic_mac_assignment(self):
        """An unknown MAC should get an IP from the dynamic pool."""
        client = BOOTPClient()
        reply = client.send_request(mac_address="ff:ee:dd:cc:bb:aa")
        self.assertIsNotNone(reply)
        self.assertNotEqual(reply.yiaddr, "0.0.0.0")

    def test_xid_matching(self):
        """The reply xid must match the request xid."""
        client = BOOTPClient()
        reply = client.send_request(mac_address="aa:bb:cc:dd:ee:02")
        self.assertIsNotNone(reply)
        self.assertEqual(reply.op, BOOTREPLY)

    def test_pool_status(self):
        """Pool status should reflect allocations."""
        status = self.server.get_pool_status()
        self.assertIn("total", status)
        self.assertIn("available", status)
        self.assertIn("allocated", status)
        self.assertGreater(status["allocated"], 0)

    def test_callback_events_fired(self):
        """Packet callbacks should have been fired."""
        # Ensure at least one request has been made to generate events
        if len(self.events) == 0:
            client = BOOTPClient()
            client.send_request(mac_address="aa:bb:cc:dd:ee:03")
            time.sleep(0.2)

        self.assertGreater(len(self.events), 0)
        event = self.events[0]
        self.assertEqual(event["protocol"], "BOOTP")
        self.assertIn(event["type"], ("BOOTREQUEST", "BOOTREPLY"))
        self.assertIn("timestamp", event)
        self.assertIn("source", event)
        self.assertIn("destination", event)
        self.assertIn("packet", event)
        self.assertIn("raw_hex", event)

    def test_server_is_running(self):
        """is_running() should return True while active."""
        self.assertTrue(self.server.is_running())


if __name__ == "__main__":
    unittest.main()
