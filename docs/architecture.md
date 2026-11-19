# System Architecture

## 1. Overview & Non-Goals

This system is a miniature BitTorrent-style Peer-to-Peer (P2P) file distribution framework engineered for learning, reliability, correctness, and empirical benchmarking.

### Core Components
1. **Tracker (HTTP Control Plane):** FastAPI web server keeping in-memory state of active swarms, registered peers, seeders/leechers, and peer heartbeats. Does **not** carry or relay file contents.
2. **Peers (TCP Data Plane):** Nodes acting simultaneously as uploaders (seeders/leechers) and downloaders over custom application-layer TCP protocol connections.
3. **Storage & Integrity Layer:** Divides files into fixed-size chunks, creates JSON manifests with SHA-256 hashes, handles chunk storage in `.part` files, and reassembles files atomically.
4. **Download Scheduler & Coordinator:** The scheduler tracks chunk states and peer availability. `SwarmDownloader` coordinates one worker per connected peer, bounded parallel requests, storage verification, retry/failover, HAVE updates, and cleanup.
5. **SwarmPeer & CLI:** `SwarmPeer` joins tracker lifecycle, listening, discovery, downloading, and verified chunk serving. The `p2p` CLI exposes tracker, manifest, seeder, and downloader commands.
6. **Tests & Benchmarks:** Unit, integration, and end-to-end correctness tests plus `bench/run_experiments.py` for isolated loopback sweeps and `bench/plot_results.py` for trial auditing, summary CSV and headless plots.

### Terms

- A **chunk** is a byte range of one file described by the manifest and verified by SHA-256.
- A **swarm** is the set of peers distributing one manifest, identified by its canonical manifest hash.
- The **tracker** stores peer addresses and lifecycle state; it never relays file bytes.
- A **seeder** has every verified chunk. A **leecher** is still downloading but can upload chunks it has verified.

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
- **Address families:** Tracker schemas accept IPv4, IPv6, and RFC 1123 hostnames. Bracketed IPv6 literals are normalized before socket bind/connect; IPv6 loopback is tested when available.

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
- **Milestone 3 implementation:** `p2p.storage.manifest` builds, validates, loads bounded JSON, atomically writes manifests, and computes the canonical Swarm ID. `p2p.storage.manager.StorageManager` owns a fresh `.part` file, verifies chunk length and SHA-256 before writing, and publishes only after the on-disk whole-file hash passes. Its methods are synchronous; callers must serialize shared access. Resume support is not implemented. Milestone 7 integrates verified chunk serving through `SwarmPeer`.

---

## 6. Milestone 6 Download Flow

`SwarmDownloader` accepts an already-connected set of `PeerConnection` objects,
a matching `DownloadScheduler`, and a `StorageManager`. It owns and closes those
connections. Tracker discovery and creation of those connections are provided by
`SwarmPeer` in Milestone 7.

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
7. When no peer can supply remaining chunks, wait up to the configured
   `availability_timeout` (default: `STALL_TIMEOUT_SEC`, 15 seconds) for a HAVE
   update; otherwise raise `NoAvailablePeersError`. Once all chunks are verified,
   finalize the file through `StorageManager.finalize()`.
8. On cancellation or any terminal error, release peer reservations and close
   all owned connections before propagating the error.

## 7. Milestone 7 Peer Lifecycle

`SwarmPeer` owns the peer TCP listener and an HTTPX client for tracker
announcements. It starts the listener before announcing, so the advertised
host/port is bound and available. The peer sends `started` on startup, follows
the tracker-returned heartbeat interval, refreshes the peer list with
`/announce`, and sends `stopped` on shutdown on a best-effort basis.

For a download, the peer refreshes discovery, tries unique candidates in
capacity-bounded batches until it fills its available outbound slots or exhausts
the list, and runs `SwarmDownloader`. Failed candidates do not prevent trying
later tracker entries. Existing inbound connections count against the same
`MAX_PEER_CONNECTIONS` budget and are not disconnected to make room. A single
per-connection reader task owns each outbound TCP read stream: it routes PIECE
messages to the worker and applies HAVE updates to scheduler availability,
including while that peer is not currently being requested. Each verified
chunk updates the listener's advertised bitfield and is announced with HAVE to
established peers. The inbound server handles requests by reading only locally
verified chunks and rechecking their manifest hash immediately before sending.
Discovery is refreshed when a download starts; this initial milestone does not
reconnect to peers that join later.

After all chunks pass whole-file verification and atomic finalization, the
leecher announces `completed` and continues to serve the completed file. The
`seed-file` and `download-file` CLI commands keep the process alive until
Ctrl+C. Shutdown cancels the heartbeat task, stops accepting connections,
cancels and awaits active connection handlers, closes peer sockets, and then
announces `stopped`. `PeerServer` waits for listener closure only after active
connections are closed.

If startup fails after resources have been created, rollback attempts to stop
the listener, always closes the tracker HTTP client, clears the server
reference, and signals the stopped event. A listener-stop or HTTP-close failure
is surfaced together with the original startup error rather than suppressing
either failure. A download with no reachable peers raises the expected
`NoAvailablePeersError`; the CLI reports it as a nonzero, traceback-free error.

## 8. Concurrency & State Ownership Rules

1. **Tracker Registry:** Owned strictly by Tracker service instance.
2. **Peer lifecycle and local verified chunks:** Owned by `SwarmPeer`; storage is the authority for which local chunks passed integrity checks.
3. **Scheduler chunk status and peer availability:** Owned by `DownloadScheduler`. Its methods are synchronous; state is not protected for cross-thread access.
4. **Per-Connection State:** Remote bitfield and active in-flight requests owned by the individual connection. For each outbound connection, one reader task owns socket reads and dispatches messages through a bounded queue.
5. **Chunk Reservation (`IN_FLIGHT`):** `reserve_next()` changes the chunk state synchronously before the worker awaits network I/O, preventing another scheduler user from reserving that chunk.
6. **Worker and Coordinator:** `DownloadWorker` owns one connection's request state; `SwarmDownloader` coordinates at most one outstanding request per peer.
7. **Storage verification:** The scheduler is marked verified only after the piece has passed `StorageManager.write_chunk()`; complete-file validation and atomic publish are delegated to `StorageManager.finalize()`.
8. **Failure and shutdown:** Retry limits are finite (default 3 attempts with a 0.05-second base delay). Failed peers are retired, reservations are released, and cancellation propagates after cleanup. The scheduler and storage manager are synchronous and intended to be used on the same event loop by this coordinator.

## 9. Testing & Measurement Architecture

- **Unit Tests:** Pure logic and focused worker tests (codec, manifest validation, path safety, scheduler decisions, retry and release behavior, fake clock expiry).
- **Integration Tests:** Loopback TCP connections (`127.0.0.1` on ephemeral ports) cover concurrent multi-peer downloads, storage finalization, corrupt-peer failover, disconnect reassignment, HAVE broadcasts, cancellation, and unavailable chunks.
- **End-to-End Tests:** FastAPI `ASGITransport` plus loopback TCP exercises one seeder and three concurrent leechers, and a staged transfer in which a completed leecher serves verified PIECE bytes to a later leecher after the original seeder stops. The tests verify final file bytes and SHA-256.
- **Client-server baseline:** `SwarmPeer(upload_enabled=False)` keeps verified
  chunks local, advertises an empty BITFIELD, suppresses HAVE in both the peer
  and downloader, and refuses incoming chunk requests even after completion.
  All baseline clients use this setting; the original seed uploads normally.
  The tracker schema and `is_seeder` completeness meaning are unchanged.
  See [ADR 0006](adr/0006-download-only-baseline.md).
- **Upload rate limiting:** `TokenBucketRateLimiter` enforces aggregate outbound
  rate limits across all connections of a peer node, supporting burst controls,
  proportional waiting for chunk transfers larger than burst capacity, and
  cancellation safety without token leakage.
- **Transfer counters:** `SwarmPeer` snapshots verified payload bytes, retry and
  chunk integrity counters, and duration after successful, failed or cancelled
  downloads. Upload counters belong to each serving peer.
  Its optional `scheduler_seed` chooses a reproducible chunk ordering (default
  zero); the benchmark uses a distinct recorded seed per client, paired by mode.
- **Benchmark Harness:** The runner owns a fresh FastAPI application/registry,
  ASGI transports, one origin and N real TCP clients per trial. All clients
  register before a common download release; completed P2P clients keep serving
  until the trial ends. Cleanup awaits every peer before removing temporary
  files. No global tracker dependency override is changed. Analysis groups
  client rows into complete trials before calculating makespan and throughput;
  upload totals repeated on client rows are counted once per trial. See
  [ADR 0008](adr/0008-in-process-benchmark-runner.md) and
  [experiment methodology](experiments.md) for controls and measurement limits.
