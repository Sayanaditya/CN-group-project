"""Database layer for packet storage using aiosqlite."""

import logging
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)


class PacketDatabase:
    """Async SQLite database for storing captured packets and protocol status.

    Attributes:
        db_path: Filesystem path to the SQLite database file.
        _db: The active aiosqlite connection (set after ``init``).
    """

    def __init__(self, db_path: str = "data/packets.db") -> None:
        """Initialise the database wrapper.

        Args:
            db_path: Path where the SQLite file will be created / opened.
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self) -> None:
        """Open the database connection and create tables if they do not exist."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        logger.info("Connected to database at %s", self.db_path)

        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS packets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol    TEXT    NOT NULL,
                type        TEXT,
                timestamp   TEXT    NOT NULL,
                source_ip   TEXT,
                source_port INTEGER,
                dest_ip     TEXT,
                dest_port   INTEGER,
                raw_hex     TEXT,
                packet_json TEXT
            )
            """
        )

        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS protocol_status (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol   TEXT    NOT NULL,
                status     TEXT    NOT NULL DEFAULT 'stopped',
                started_at TEXT,
                stopped_at TEXT
            )
            """
        )
        await self._db.commit()
        logger.info("Database tables verified / created.")

    # ------------------------------------------------------------------
    # Packet operations
    # ------------------------------------------------------------------

    async def insert_packet(self, packet_event: dict) -> None:
        """Insert a single packet event into the ``packets`` table.

        Args:
            packet_event: Dictionary whose keys map to column names.
        """
        source = packet_event.get("source", {})
        destination = packet_event.get("destination", {})
        packet_data = packet_event.get("packet", {})

        import json as _json
        packet_json_str = _json.dumps(packet_data, default=str) if packet_data else ""

        await self._db.execute(
            """
            INSERT INTO packets
                (protocol, type, timestamp, source_ip, source_port,
                 dest_ip, dest_port, raw_hex, packet_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                packet_event.get("protocol", ""),
                packet_event.get("type", ""),
                packet_event.get("timestamp", datetime.now(timezone.utc).isoformat()),
                source.get("ip", ""),
                source.get("port"),
                destination.get("ip", ""),
                destination.get("port"),
                packet_event.get("raw_hex", ""),
                packet_json_str,
            ),
        )
        await self._db.commit()

    async def get_packets(
        self, protocol: Optional[str] = None, limit: int = 100
    ) -> list[dict]:
        """Retrieve packets, optionally filtered by protocol.

        Args:
            protocol: If supplied, only return packets of this protocol.
            limit: Maximum number of rows to return (newest first).

        Returns:
            A list of packet-event dictionaries.
        """
        if protocol:
            cursor = await self._db.execute(
                "SELECT * FROM packets WHERE protocol = ? ORDER BY id DESC LIMIT ?",
                (protocol, limit),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM packets ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Protocol-status operations
    # ------------------------------------------------------------------

    async def update_protocol_status(self, protocol: str, status: str) -> None:
        """Upsert the running/stopped status of a protocol.

        If a row for *protocol* already exists it is updated; otherwise a new
        row is inserted.

        Args:
            protocol: Protocol name (e.g. ``"bootp"``).
            status: ``"running"`` or ``"stopped"``.
        """
        now = datetime.now(timezone.utc).isoformat()

        cursor = await self._db.execute(
            "SELECT id FROM protocol_status WHERE protocol = ?", (protocol,)
        )
        row = await cursor.fetchone()

        if row:
            if status == "running":
                await self._db.execute(
                    "UPDATE protocol_status SET status = ?, started_at = ? WHERE protocol = ?",
                    (status, now, protocol),
                )
            else:
                await self._db.execute(
                    "UPDATE protocol_status SET status = ?, stopped_at = ? WHERE protocol = ?",
                    (status, now, protocol),
                )
        else:
            started = now if status == "running" else None
            stopped = now if status == "stopped" else None
            await self._db.execute(
                """
                INSERT INTO protocol_status (protocol, status, started_at, stopped_at)
                VALUES (?, ?, ?, ?)
                """,
                (protocol, status, started, stopped),
            )
        await self._db.commit()

    async def get_protocol_status(
        self, protocol: Optional[str] = None
    ) -> list[dict]:
        """Get the status of one or all protocols.

        Args:
            protocol: If supplied, filter to this protocol only.

        Returns:
            A list of protocol-status dictionaries.
        """
        if protocol:
            cursor = await self._db.execute(
                "SELECT * FROM protocol_status WHERE protocol = ?", (protocol,)
            )
        else:
            cursor = await self._db.execute("SELECT * FROM protocol_status")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Aggregate statistics
    # ------------------------------------------------------------------

    async def get_stats(self) -> dict:
        """Return aggregate packet statistics.

        Returns:
            A dict containing ``total_packets``, ``per_protocol`` counts,
            and ``protocol_statuses``.
        """
        cursor = await self._db.execute("SELECT COUNT(*) as total FROM packets")
        total_row = await cursor.fetchone()
        total: int = total_row["total"] if total_row else 0

        cursor = await self._db.execute(
            "SELECT protocol, COUNT(*) as count FROM packets GROUP BY protocol"
        )
        per_protocol: dict[str, int] = {
            row["protocol"]: row["count"] for row in await cursor.fetchall()
        }

        statuses = await self.get_protocol_status()

        return {
            "total_packets": total,
            "per_protocol": per_protocol,
            "protocol_statuses": statuses,
        }
