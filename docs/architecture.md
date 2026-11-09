# System Architecture

## 1. Overview & Non-Goals

This system is a miniature BitTorrent-style Peer-to-Peer (P2P) file distribution framework engineered for learning, reliability, correctness, and empirical benchmarking.

### Core Components
1. **Tracker (HTTP Control Plane):** FastAPI web server keeping in-memory state of active swarms, registered peers, seeders/leechers, and peer heartbeats. Does **not** carry or relay file contents.
2. **Peers (TCP Data Plane):** Nodes acting simultaneously as uploaders (seeders/leechers) and downloaders over custom application-layer TCP protocol connections.
3. **Storage & Integrity Layer:** Divides files into fixed-size chunks, creates JSON manifests with SHA-256 hashes, handles chunk storage in `.part` files, and reassembles files atomically.
4. **Download Scheduler & Coordinator:** The scheduler tracks chunk states and peer availability. `SwarmDownloader` coordinates one worker per already-connected peer, bounded parallel requests, storage verification, retry/failover, HAVE updates, and cleanup. Tracker discovery and CLI integration are Milestone 7 work.
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
  - `POST /announce`: Accepts peer announcements (`swarm_id`, `peer_id`, `host`, `port`, `event`, optional `is_seeder`). Events: `started`, `heartbeat`, `completed`, `stopped`. Returns the 30-second heartbeat interval and at most 50 active peers (excluding caller). Unknown heartbeat announcements register the peer, allowing recovery after a tracker restart.
  - `GET /swarms/{swarm_id}/peers`: Requires a 64-character lowercase hexadecimal swarm ID and returns active peers (`peer_id`, `host`, `port`, `last_seen`, `is_seeder`). A valid but unknown swarm returns an empty list.
  - `GET /health`: Basic health check.
- **Peer Expiry:** In-memory registry tracks `last_seen` timestamp using an injectable monotonic clock interface. Peers inactive for more than `3 * heartbeat_interval` (default interval: 30s, expiry: 90s) are evicted lazily during announce/list operations or by an explicit registry eviction call. Peers exactly 90 seconds old remain active.
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
- **Milestone 5 implementation:** `p2p.peer.connection.PeerConnection` encapsulates the 5-state lifecycle (`UNCONNECTED`, `AWAIT_HANDSHAKE`, `AWAIT_BITFIELD`, `STEADY_STATE`, `CLOSED`), in-flight request bounding (`MAX_INFLIGHT_PER_PEER`), serialized writes with `asyncio.Lock`, and automatic socket cleanup. `p2p.peer.server.PeerServer` provides an async TCP listener for peer swarms with ephemeral port binding, concurrent connection tracking, and graceful shutdown.

---

## 5. Storage & Integrity Boundary

- Remote peer data is **untrusted**.
- **Manifest:** JSON file specifying `file_name`, `file_size`, `chunk_size`, `chunk_count`, `file_sha256`, and per-chunk `sha256` array.
- **Swarm ID:** Derived canonically via `sha256(canonical_json_manifest_bytes)`.
- **Chunk Acceptance:** A received piece is written to `<filename>.part` at offset `index * chunk_size` **only after** verifying chunk length and SHA-256 hash match the manifest.
- **Safe Paths:** Manifest filenames are sanitized to prevent directory traversal (`safe_target()` checks).
- **Atomic Finalization:** Once all chunks are verified, whole-file SHA-256 is checked against `file_sha256`, followed by atomic rename (`os.replace`) to the final destination.
- **Milestone 3 implementation:** `p2p.storage.manifest` builds, validates, loads bounded JSON, atomically writes manifests, and computes the canonical Swarm ID. `p2p.storage.manager.StorageManager` owns a fresh `.part` file, verifies chunk length and SHA-256 before writing, and publishes only after the on-disk whole-file hash passes. Its methods are synchronous; callers must serialize shared access. Resume and peer-serving integration are not implemented.

---

## 6. Milestone 6 Download Flow

`SwarmDownloader` accepts an already-connected set of `PeerConnection` objects,
a matching `DownloadScheduler`, and a `StorageManager`. It owns and closes those
connections. Tracker discovery and creation of those connections are outside its
scope.

1. Register each peer's handshake bitfield with the scheduler.
2. Select peers that advertise a `MISSING` chunk. The scheduler makes a seeded
   random choice among that peer's eligible chunks (default seed: `0`).
3. Reserve synchronously before network I/O. Run one request per eligible peer
   concurrently, up to `MAX_GLOBAL_INFLIGHT`; the system also caps connections
   at `MAX_PEER_CONNECTIONS`. Each worker is sequential and therefore permits
   one in-flight request per peer.
4. While waiting for the requested `PIECE`, process incoming `HAVE` messages as
   peer availability updates. Unexpected message types fail that transfer.
5. Write each piece through `StorageManager.write_chunk()`. A chunk becomes
   `VERIFIED` only after storage validates its length and SHA-256. Broadcast
   `HAVE` for the verified index to other active peers.
6. Retry a failed chunk on its current peer up to `max_retries` with exponential
   delay. The reservation remains in-flight during retries. On exhausted retry
   or peer failure, release it and retire that peer; another active peer may then
   receive the chunk.
7. When no peer can supply remaining chunks, raise `NoAvailablePeersError`
   rather than waiting indefinitely. Once all chunks are verified, finalize the
   file through `StorageManager.finalize()`.
8. On cancellation or any terminal error, release peer reservations and close
   all owned connections before propagating the error.

## 7. Concurrency & State Ownership Rules

1. **Tracker Registry:** Owned strictly by Tracker service instance.
2. **Local Chunk Status and Peer Availability:** Owned by `DownloadScheduler`. Its methods are synchronous; state is not protected for cross-thread access.
3. **Per-Connection State:** Remote bitfield and active in-flight requests owned by the individual connection session handler.
4. **Chunk Reservation (`IN_FLIGHT`):** `reserve_next()` changes the chunk state synchronously before the worker awaits network I/O, preventing another scheduler user from reserving that chunk.
5. **Worker and Coordinator:** `DownloadWorker` owns one connection's request loop; `SwarmDownloader` owns the supplied connected peers and coordinates at most one outstanding request per peer.
6. **Storage verification:** Storage is required. The scheduler is marked verified only after the piece has passed `StorageManager.write_chunk()`; complete-file validation and atomic publish are delegated to `StorageManager.finalize()`.
7. **Failure and shutdown:** Retry limits are finite (default 3 attempts with a 0.05-second base delay). Failed peers are removed from the active set, reservations are released, and cancellation propagates after cleanup. The scheduler and storage manager are synchronous and intended to be used on the same event loop by this coordinator.

## 8. Testing & Measurement Architecture

- **Unit Tests:** Pure logic and focused worker tests (codec, manifest validation, path safety, scheduler decisions, retry and release behavior, fake clock expiry).
- **Integration Tests:** Loopback TCP connections (`127.0.0.1` on ephemeral ports) cover concurrent multi-peer downloads, storage finalization, corrupt-peer failover, disconnect reassignment, HAVE broadcasts, cancellation, and unavailable chunks.
- **End-to-End Tests:** Full tracker discovery, seeder, and multiple leecher workflows remain Milestone 7.
- **Benchmark Harness:** Standard CSV dataset generator and Matplotlib plotting scripts comparing client-server vs P2P runs under bandwidth limits.
