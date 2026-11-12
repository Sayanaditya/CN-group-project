# 📋 Roll 08 (Sayanaditya Das) — Implementation & Integration Guide

**Role:** BOOTP Protocol Lead & Core Backend / Data Engine (28% Weightage)  
**Branch:** `sayanaditya`  
**Date:** November 2026  

---

## 1. Overview of Completed Work

As assigned in the project plan, **Roll 08** is responsible for:
1. **Full BOOTP Protocol Implementation (RFC 951)** — Binary packet serialization/deserialization, multithreaded UDP Server with static IP mapping & dynamic IP address pool allocation, and BOOTP Client.
2. **Centralized Data & Logging Pipeline** — Asynchronous SQLite database (`aiosqlite`) and thread-safe real-time `PacketLogger` event hub.
3. **Core FastAPI Backend Framework** — REST endpoints, WebSocket streaming pipeline, CORS handling, static asset mounting, and application lifecycle management.
4. **Integration Stubs & Contracts** — Ready-to-use API routes and WebSocket bridge contracts for **Roll 11** (DNS) and **Roll 14** (Telnet), plus live event hooks for **Roll 27** (Frontend Visualizer).
5. **Unit & Integration Test Suite** — Comprehensive `unittest` suite verifying RFC compliance, packet round-trip packing, IP leases, and callbacks.

---

## 2. File & Directory Structure Created

```text
group-project/
├── requirements.txt                  # Backend dependencies (fastapi, uvicorn, etc.)
├── run.py                            # Single entry point: python run.py
├── data/
│   ├── bootp_pool.json               # Configurable BOOTP dynamic pool & static MAC reservations
│   ├── zone.txt                      # Seed DNS zone file (for Roll 11)
│   └── users.json                    # Seed Telnet credentials (for Roll 14)
├── protocols/
│   ├── __init__.py
│   └── bootp/
│       ├── __init__.py               # Exports BOOTPPacket, BOOTPServer, BOOTPClient, config
│       ├── config.py                 # Ports (10067/10068), defaults, static MAC mappings
│       ├── packet.py                 # RFC 951 300-byte fixed struct packing/unpacking & hex dump
│       ├── server.py                 # Threaded UDP server, IP pool manager, callback hooks
│       └── client.py                 # UDP client, auto-MAC detection, xid verification
├── logger/
│   ├── __init__.py
│   ├── db.py                         # Async SQLite (PacketDatabase) with packets & status tables
│   └── packet_logger.py              # Singleton PacketLogger + ThreadSafe callback bridge
├── backend/
│   ├── __init__.py
│   ├── app.py                        # Main FastAPI app, lifespan handler, CORS, /api/status, static mount
│   ├── models.py                     # Pydantic models (PacketEvent, BOOTPConfig, ApiResponse, etc.)
│   ├── websocket.py                  # WebSocketManager broadcasting real-time events to frontend
│   └── routes/
│       ├── __init__.py
│       ├── bootp_routes.py           # Fully implemented BOOTP start/stop/request/pool/logs endpoints
│       ├── dns_routes.py             # Stub routes with clear TODOs for Roll 11
│       └── telnet_routes.py          # Stub routes with clear TODOs for Roll 14
├── frontend/
│   └── index.html                    # Placeholder landing page for Roll 27's SPA
└── tests/
    ├── __init__.py
    └── test_bootp.py                 # 11 unit & integration tests covering BOOTP (100% passing)
```

---

## 3. Detailed Component Documentation

### 3.1 BOOTP Protocol (`protocols/bootp/`)
- **`packet.py`**:
  - Encodes and decodes the **exact 300-byte** binary format defined in RFC 951 using `struct.pack("!BBBB I HH 4s4s4s4s 16s 64s 128s")` + 64-byte vendor area.
  - Implements `MAGIC_COOKIE` (`99.130.83.99` / RFC 1048).
  - Includes `to_dict()` for frontend JSON serialization and `hex_dump()` for wireshark-style inspection.
- **`server.py`**:
  - Runs in a background daemon thread, listening on UDP port `10067` (non-privileged).
  - Maintains `_allocations` and `_available_ips` safely with a `threading.Lock`.
  - Checks static MAC reservations first (from `data/bootp_pool.json` or `config.py`), then falls back to dynamic range `192.168.1.100 - 192.168.1.200`.
  - Emits structured event dictionaries via `on_packet_callback` for every `BOOTREQUEST` and `BOOTREPLY`.
- **`client.py`**:
  - Binds to UDP port `10068` and sends broadcast/unicast `BOOTREQUEST` with a randomly generated 32-bit transaction ID (`xid`).
  - Automatically discovers host MAC address or falls back to locally-administered MAC.
  - Validates matching `xid` and `BOOTREPLY` opcode before returning.

### 3.2 Data Layer & Packet Logger (`logger/`)
- **`logger/db.py` (`PacketDatabase`)**:
  - Uses `aiosqlite` to store all captured packets and module statuses in `data/packets.db`.
  - Schema:
    - `packets`: `id`, `protocol`, `type`, `timestamp`, `source_ip`, `source_port`, `dest_ip`, `dest_port`, `raw_hex`, `packet_json`.
    - `protocol_status`: `id`, `protocol`, `status`, `started_at`, `stopped_at`.
  - Methods: `insert_packet()`, `get_packets(protocol, limit)`, `update_protocol_status()`, `get_stats()`.
- **`logger/packet_logger.py` (`PacketLogger`)**:
  - Singleton pattern.
  - **Thread-safe bridge**: Because protocol servers run in synchronous worker threads while FastAPI/WebSockets run on an `asyncio` event loop, `get_callback_for_protocol(protocol)` returns a thread-safe synchronous callback that internally executes `asyncio.run_coroutine_threadsafe(self.log_packet(event), loop)`.
  - Forwards all logged packets to registered WebSocket broadcast listeners.

### 3.3 Backend API & WebSockets (`backend/`)
- **`backend/websocket.py`**:
  - Manages frontend client connections and fans out live packet notifications to all connected browsers.
- **`backend/app.py`**:
  - Initializes DB and wires logger on startup using the modern `lifespan` context manager.
  - Serves REST endpoints under `/api/...` and live WebSocket streaming under `/ws/packets`.
  - Mounts `frontend/` as a static directory at `/` without intercepting API routes.

---

## 4. Instructions for Teammates (Merge & Integration)

### 🧑 For Roll 11 (DNS Lead):
1. **Implement your protocol in** `protocols/dns/`:
   - Follow the structure used in `protocols/bootp/`: `packet.py`, `server.py`, `client.py`, `zone.py`.
   - Set server port to `10053` (non-privileged) for easy testing without `sudo`.
2. **Hook into the Backend in** `backend/routes/dns_routes.py`:
   - Replace the `_NOT_IMPL` responses.
   - To capture packets for the visualizer, wire your server and client using:
     ```python
     from logger.packet_logger import PacketLogger
     callback = PacketLogger.get_instance().get_callback_for_protocol("dns")
     server = DNSServer(..., on_packet_callback=callback)
     ```
   - Update protocol state using:
     ```python
     await PacketLogger.get_instance()._db.update_protocol_status("dns", "running")
     ```
3. Use `data/zone.txt` as your default zone file.

---

### 🧑 For Roll 14 (Telnet Lead):
1. **Implement your protocol in** `protocols/telnet/`:
   - Build `server.py`, `client.py`, `negotiation.py` (IAC option handling), and `commands.py`.
   - Set default port to `2323`.
2. **Hook into the Backend in** `backend/routes/telnet_routes.py`:
   - Wire your server/client callbacks via:
     ```python
     from logger.packet_logger import PacketLogger
     callback = PacketLogger.get_instance().get_callback_for_protocol("telnet")
     server = TelnetServer(..., on_packet_callback=callback)
     ```
3. **Interactive Terminal Integration (`backend/app.py`)**:
   - In `backend/app.py`, update the `@app.websocket("/ws/telnet")` endpoint to bridge browser terminal keystrokes to your virtual Telnet shell session.
4. Use `data/users.json` for user authentication.

---

### 🧑 For Roll 27 (Frontend & Visualizer Lead):
1. **Web Directory**:
   - Place your HTML, CSS, JavaScript (or compiled React bundle) directly in `frontend/`. `backend/app.py` automatically serves `frontend/index.html` at `http://localhost:8000/`.
2. **Live WebSocket Stream**:
   - Connect to `ws://localhost:8000/ws/packets`.
   - You will receive real-time JSON objects structured as:
     ```json
     {
       "protocol": "BOOTP",
       "type": "BOOTREQUEST" | "BOOTREPLY",
       "timestamp": "2026-11-10T19:53:08.123456+00:00",
       "source": {"ip": "127.0.0.1", "port": 10068},
       "destination": {"ip": "127.0.0.1", "port": 10067},
       "packet": {
         "op": 1,
         "op_name": "BOOTREQUEST",
         "htype": 1,
         "hlen": 6,
         "hops": 0,
         "xid": "0xc80846eb",
         "secs": 0,
         "flags": "0x8000",
         "ciaddr": "0.0.0.0",
         "yiaddr": "0.0.0.0",
         "siaddr": "0.0.0.0",
         "giaddr": "0.0.0.0",
         "chaddr": "aa:bb:cc:dd:ee:01",
         "sname": "",
         "file": "",
         "vend_hex": "..."
       },
       "raw_hex": "0000  01 01 06 00 c8 08 46 eb ...  ......F."
     }
     ```
3. **BOOTP REST Endpoints Available**:
   - `POST /api/bootp/start-server` — starts server
   - `POST /api/bootp/stop-server` — stops server
   - `POST /api/bootp/send-request?mac_address=aa:bb:cc:dd:ee:01` — triggers a test request
   - `GET /api/bootp/pool` — get pool configuration
   - `GET /api/bootp/allocations` — get active MAC-to-IP leases
   - `GET /api/bootp/logs?limit=50` — get historical packet logs from SQLite
   - `GET /api/status` — get overall system and protocol statuses

---

## 5. Verification & Testing

To run the BOOTP and infrastructure unit tests:
```bash
python3 -m unittest tests.test_bootp -v
```

All 11 tests pass:
- Fixed 300-byte binary serialization & round-trip verification
- Header decoding & hex dump accuracy
- Static reservation lookup (`aa:bb:cc:dd:ee:01` -> `192.168.1.10`)
- Dynamic IP address leasing from pool
- Transaction ID (`xid`) matching between client and server
- Event callback generation and field verification

To run the full application:
```bash
python3 run.py
```
Then visit `http://localhost:8000` or inspect the auto-generated Swagger documentation at `http://localhost:8000/docs`.

---

## 6. How to Merge to `main`

1. Stage all changes:
   ```bash
   git add .
   ```
2. Commit with descriptive message:
   ```bash
   git commit -m "feat(bootp, backend): implement BOOTP protocol, logging engine, and core FastAPI backend"
   ```
3. Push branch to GitHub:
   ```bash
   git push origin sayanaditya
   ```
4. Create a Pull Request into `main`. Since all modules are namespaced (`protocols/bootp/`, `backend/routes/bootp_routes.py`, `logger/`), there will be **zero merge conflicts** with Roll 11, Roll 14, or Roll 27.
