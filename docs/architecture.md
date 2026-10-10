# System Architecture

## 1. Overview & Non-Goals

This system is a miniature BitTorrent-style Peer-to-Peer (P2P) file distribution framework engineered for learning, reliability, correctness, and empirical benchmarking.

### Core Components
1. **Tracker (HTTP Control Plane):** FastAPI web server keeping in-memory state of active swarms, registered peers, seeders/leechers, and peer heartbeats. Does **not** carry or relay file contents.
2. **Peers (TCP Data Plane):** Nodes acting simultaneously as uploaders (seeders/leechers) and downloaders over custom application-layer TCP protocol connections.
3. **Storage & Integrity Layer:** Divides files into fixed-size chunks, creates JSON manifests with SHA-256 hashes, handles chunk storage in `.part` files, and reassembles files atomically.
4. **Download Scheduler & Swarm Orchestrator:** Manages peer discovery, connection pools, chunk reservation, parallel downloading, retries, and HAVE broadcasts.
5. **Benchmark & Test Harness:** Automated scripts to measure makespan, throughput, peer upload contribution, and compare against a client-server baseline.

### Non-Goals
- Databases, Redis, message queues, Docker, cloud infrastructure, or frontend UIs.
- NAT traversal, DHT, TLS/encryption, or multi-file torrents.
- AI/ML algorithms inside the core system.

---

## 2. Component Boundaries & Responsibilities

```
+------------------------------------------------------------------------+
|                            TRACKER SERVICE                             |
|  (FastAPI HTTP Control Plane: Announce, Swarm Registry, Health)        |
+-----------------------------------+------------------------------------+
                                    | HTTP (Announce / Peer Discovery)
                                    v
+------------------------------------------------------------------------+
|                               PEER NODE                                |
|                                                                        |
|  +------------------------+          +------------------------------+  |
|  |   Download Scheduler   |          |    Peer Connection Manager   |  |
|  | (Chunk selection,      |<-------->| (TCP streams, framing codec, |  |
|  |  reservations, retries)|          |  handshakes, bitfields)      |  |
|  +-----------+------------+          +--------------+---------------+  |
|              |                                      |                  |
|              v                                      v                  |
|  +------------------------+          +------------------------------+  |
|  |  Storage & Integrity   |          |       Wire Protocol Codec    |  |
|  | (SHA-256 verification, |          | (HANDSHAKE, BITFIELD,        |  |
|  |  .part files, reassembly)|         |  REQUEST, PIECE, HAVE)       |  |
|  +------------------------+          +------------------------------+  |
+-----------------------------------+------------------------------------+
                                    | TCP (Data Plane - Piece Transfers)
                                    v
                            (Remote Peer Nodes)
```

---

## 3. Control Plane: Tracker Semantics

The Tracker coordinates peer discovery:
- **Endpoints:**
  - `POST /announce`: Accepts peer announcements (`swarm_id`, `peer_id`, `host`, `port`, `event`). Events: `started`, `heartbeat`, `completed`, `stopped`. Returns interval and a list of active peers (excluding caller).
  - `GET /swarms/{swarm_id}/peers`: Returns list of peers in a swarm (`peer_id`, `host`, `port`, `last_seen`, `is_seeder`).
  - `GET /health`: Basic health check.
- **Peer Expiry:** In-memory registry tracks `last_seen` timestamp using an injectable clock interface. Peers inactive for `3 * heartbeat_interval` (default interval: 30s) are marked stale and evicted.
- **Peer Address Handling:** LAN testing uses advertised `host`/`port` provided in `/announce`.

---

## 4. Data Plane: Peer-to-Peer TCP Communications

- **Dual Role:** A peer is both a TCP server (listening for incoming connections on `listen_port`) and a TCP client (connecting out to discovered peers).
- **Framing:** Length-prefixed binary frames (big-endian `uint32` length + `uint8` message code + payload).
- **State Machine:**
  1. Connection established.
  2. Both sides exchange `HANDSHAKE` (validate `version`, `swarm_id`, `peer_id`).
  3. Both sides send `BITFIELD` (chunk availability).
  4. Steady state: `REQUEST` <-> `PIECE` exchange; `HAVE` broadcasts on verified chunk arrival.
  5. Connection termination: clean close or abort on protocol error.

---

## 5. Storage & Integrity Boundary

- Remote peer data is **untrusted**.
- **Manifest:** JSON file specifying `file_name`, `file_size`, `chunk_size`, `chunk_count`, `file_sha256`, and per-chunk `sha256` array.
- **Swarm ID:** Derived canonically via `sha256(canonical_json_manifest_bytes)`.
- **Chunk Acceptance:** A received piece is written to `<filename>.part` at offset `index * chunk_size` **only after** verifying chunk length and SHA-256 hash match the manifest.
- **Safe Paths:** Manifest filenames are sanitized to prevent directory traversal (`safe_target()` checks).
- **Atomic Finalization:** Once all chunks are verified, whole-file SHA-256 is checked against `file_sha256`, followed by atomic rename (`os.replace`) to the final destination.

---

## 6. Concurrency & State Ownership Rules

1. **Tracker Registry:** Owned strictly by Tracker service instance.
2. **Local Chunk Status/Bitfield:** Owned by `DownloadScheduler`. Connection handlers read/query via thread-safe async interfaces.
3. **Per-Connection State:** Remote bitfield and active in-flight requests owned by the individual connection session handler.
4. **Chunk Reservation (`IN_FLIGHT`):** A chunk index is marked `IN_FLIGHT` synchronously *before* an `await` point to avoid duplicate fetching across concurrent peer tasks.
5. **Task Cleanup:** All network tasks use `asyncio.TaskGroup` or tracked task sets with timeouts. No orphan tasks or leaked sockets.

---

## 7. Testing & Measurement Architecture

- **Unit Tests:** Pure logic (codec, manifest validation, path safety, scheduler decisions, fake clock expiry).
- **Integration Tests:** Loopback TCP socket connections (`127.0.0.1` on port `0`), ephemeral ports, FastAPI `TestClient`/ASGI transport.
- **End-to-End Tests:** Loopback multi-peer swarms downloading real files, asserting bit-for-bit file SHA-256 equivalence.
- **Benchmark Harness:** Standard CSV dataset generator and Matplotlib plotting scripts comparing client-server vs P2P runs under bandwidth limits.
