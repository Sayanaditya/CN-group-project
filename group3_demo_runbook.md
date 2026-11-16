# Group 3 — Protocol Visualizer Demo & Multi-Device Runbook

**Protocols:** BOOTP (RFC 951 · UDP `10067`/`10068`) · DNS (RFC 1035 · UDP/TCP `10053`) · TELNET (RFC 854 · TCP `2323`)  
**Dashboard & WebSocket Port:** `8000`

---

## 1. Laptop Server Setup (Run Once per Session)

### Check Your Laptop's Current Wi-Fi IP & Subnet Broadcast
Whenever you switch to a new Wi-Fi or mobile hotspot, run:
```bash
hostname -I                  # Use the first 192.168.x.x / 10.x.x.x IP as <LAPTOP_IP>
ip -4 addr show | grep brd   # Shows your subnet broadcast (e.g. 192.168.29.255)
```

### Open Firewall Ports (One-Time on Ubuntu)
```bash
sudo ufw allow 8000/tcp
sudo ufw allow 10067/udp
sudo ufw allow 10068/udp
sudo ufw allow 10053/udp
sudo ufw allow 10053/tcp
sudo ufw allow 2323/tcp
```

### Start the Server (Clean State)
```bash
cd ~/CN-group-project
source .venv/bin/activate

# Optional: clear old packet history before a fresh demo
rm -f data/packets.db

# Clear any leftover C telnet-server holding port 2323
pkill -9 telnet-server 2>/dev/null || true

# Start FastAPI + WebSockets + Roll 27 Frontend
python3 run.py
```

### Start All 3 Protocol Servers
Open **`http://localhost:8000`** and click **Start** on **BOOTP**, **DNS**, and **Telnet**, or trigger all three from another laptop terminal:
```bash
curl -s -X POST http://localhost:8000/api/bootp/start-server
curl -s -X POST http://localhost:8000/api/dns/start-server
curl -s -X POST http://localhost:8000/api/telnet/start-server
```

Verify all ports are listening:
```bash
ss -ulnp | grep -E '10067|10053'
ss -tlnp | grep -E '8000|10053|2323|2324'
```

---

## 2. Client Commands from Other Terminals on the Same Laptop

### BOOTP (RFC 951)
```bash
# Static MAC reservation (192.168.1.10)
curl -s -X POST "http://localhost:8000/api/bootp/send-request?mac_address=aa:bb:cc:dd:ee:01"

# Dynamic pool lease (192.168.1.100+)
curl -s -X POST "http://localhost:8000/api/bootp/send-request?mac_address=02:42:ac:11:00:05"
```

### DNS (RFC 1035 — UDP & TCP)
```bash
python3 -m protocols.dns.client example.local --server 127.0.0.1 --port 10053 --type A
python3 -m protocols.dns.client example.local --server 127.0.0.1 --port 10053 --type MX
python3 -m protocols.dns.client www.example.local --server 127.0.0.1 --port 10053 --type CNAME
python3 -m protocols.dns.client example.local --server 127.0.0.1 --port 10053 --type NS
python3 -m protocols.dns.client example.local --server 127.0.0.1 --port 10053 --tcp
```

### TELNET (RFC 854)
```bash
./telnet/bin/telnet-client 127.0.0.1 2323
```
Inside the session, run `whoami`, `pwd`, `ls`, `echo $TERM`. Press `Ctrl + ]` then `quit` to exit.

---

## 3. Client Commands from Other Devices on the Same Wi-Fi

Replace `<LAPTOP_IP>` with the Wi-Fi IP from `hostname -I`.

### Web Visualizer (Any Phone or Laptop Browser)
Open **`http://<LAPTOP_IP>:8000`** to view the live Dashboard, Sequence Diagram, Header Decoder, and `xterm.js` terminal.

### Android Termux One-Time Package Setup
```bash
pkg update -y && pkg install -y python busybox
```

### BOOTP Broadcast (`bootp_true_client.py`)
Create `bootp_true_client.py` on each client device:
```bash
cat << 'EOF' > bootp_true_client.py
import os
import socket
import struct
import sys
import time
import uuid

# Usage: python3 bootp_true_client.py [MAC_ADDRESS] [BROADCAST_IP]
if len(sys.argv) > 1:
    mac_str = sys.argv[1]
else:
    node = uuid.getnode()
    mac_str = ":".join(f"{(node >> i) & 0xff:02x}" for i in range(40, -1, -8))

broadcast_ip = sys.argv[2] if len(sys.argv) > 2 else "255.255.255.255"

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("0.0.0.0", 10068))
sock.settimeout(4.0)

xid = int.from_bytes(os.urandom(4), "big")
mac_bytes = bytes.fromhex(mac_str.replace(":", ""))

pkt = (
    struct.pack(
        "!BBBB I HH 4s4s4s4s 16s 64s 128s",
        1, 1, 6, 0, xid, 0, 0x8000,
        b"\x00" * 4, b"\x00" * 4, b"\x00" * 4, b"\x00" * 4,
        mac_bytes.ljust(16, b"\x00"), b"\x00" * 64, b"\x00" * 128,
    )
    + b"\x63\x82\x53\x63\xff"
    + b"\x00" * 59
)

sock.sendto(pkt, (broadcast_ip, 10067))
print(f"[Client] Broadcast BOOTREQUEST | MAC={mac_str} | xid={hex(xid)} -> {broadcast_ip}:10067")

deadline = time.time() + 4.0
while time.time() < deadline:
    try:
        data, addr = sock.recvfrom(1024)
        if len(data) >= 300 and data[0] == 2:
            rep_xid = struct.unpack("!I", data[4:8])[0]
            yiaddr = socket.inet_ntoa(data[16:20])
            if rep_xid == xid:
                print(f"[Client] ACCEPTED BOOTREPLY from {addr[0]} | xid={hex(rep_xid)} | Assigned IP={yiaddr}")
                break
            else:
                print(f"[Client] Ignored broadcast BOOTREPLY for another client (xid={hex(rep_xid)})")
    except socket.timeout:
        print("[Client] Timed out waiting for BOOTREPLY.")
        break
EOF
```

Run from multiple devices:
```bash
python3 bootp_true_client.py 11:22:33:44:55:01
python3 bootp_true_client.py 11:22:33:44:55:02
python3 bootp_true_client.py aa:bb:cc:dd:ee:01   # Hits static reservation (.10)
```

### DNS Query Script (`dns_query_client.py`)
Create `dns_query_client.py` on Termux or another laptop (supports both UDP and TCP):
```bash
cat << 'EOF' > dns_query_client.py
import socket
import struct
import sys

# Usage: python3 dns_query_client.py <LAPTOP_IP> [DOMAIN] [QTYPE] [--tcp]
server_ip = sys.argv[1]
domain = sys.argv[2] if len(sys.argv) > 2 else "example.local"
qtype_name = sys.argv[3].upper() if len(sys.argv) > 3 else "A"
use_tcp = "--tcp" in sys.argv

qtypes = {"A": 1, "NS": 2, "CNAME": 5, "MX": 15, "AAAA": 28}
qname = b"".join(bytes([len(p)]) + p.encode() for p in domain.rstrip(".").split(".")) + b"\x00"
pkt = struct.pack("!HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0) + qname + struct.pack("!HH", qtypes.get(qtype_name, 1), 1)

if use_tcp:
    s = socket.create_connection((server_ip, 10053), timeout=3.0)
    s.sendall(struct.pack("!H", len(pkt)) + pkt)
    size = struct.unpack("!H", s.recv(2))[0]
    resp = s.recv(size)
    s.close()
    proto = "TCP"
else:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3.0)
    s.sendto(pkt, (server_ip, 10053))
    resp, _ = s.recvfrom(4096)
    s.close()
    proto = "UDP"

rcode = struct.unpack("!H", resp[2:4])[0] & 0x0F
ancount = struct.unpack("!H", resp[6:8])[0]
print(f"[{proto}] {domain} ({qtype_name}) -> {len(resp)} bytes | RCODE={rcode} | ANCOUNT={ancount}")
EOF
```

Run from other devices:
```bash
python3 dns_query_client.py <LAPTOP_IP> example.local A
python3 dns_query_client.py <LAPTOP_IP> example.local MX
python3 dns_query_client.py <LAPTOP_IP> example.local A --tcp
```
*(Or on another Linux/macOS laptop with `dig`: `dig @<LAPTOP_IP> -p 10053 example.local A`.)*

### TELNET Client
* **Android (Termux):**
  ```bash
  busybox telnet <LAPTOP_IP> 2323
  ```
* **Another Linux / macOS Laptop:**
  ```bash
  telnet <LAPTOP_IP> 2323
  ```

---

## 4. Quick Troubleshooting
* **Campus/Public Wi-Fi drops packets between devices:** Router **AP/Client Isolation** is blocking peer-to-peer traffic. Connect your laptops to your **phone's mobile hotspot** instead.
* **`Connection refused` on Telnet (`2323`):** Ensure you clicked **▶ Start (:2323)** in the Dashboard and run `pkill -9 telnet-server` before restarting `python3 run.py` if an old C process was stuck.
* **Browser shows old UI:** Hard-refresh with **`Ctrl + Shift + R`**.
* **Android Termux `cannot bind netlink socket`:** `ip addr` is blocked by Android 11+; check your phone's IP via **Settings → Wi-Fi** or `python3 -c 'import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(("8.8.8.8",80)); print(s.getsockname()[0])'`.
