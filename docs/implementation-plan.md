# Project Implementation Plan & Milestones

This document outlines the small, testable implementation milestones for the P2P File Distribution System. Each milestone contains explicit deliverables and acceptance criteria.

---

## Milestone Status Overview

- [x] **Milestone 1: Project Foundation & Environment Setup** (**COMPLETED** - 2026-10-10)
- [x] **Milestone 2: Wire Framing Codec & Protocol Messages** (**COMPLETED** - 2026-10-11)
- [x] **Milestone 3: Manifest Engine & Storage Integrity** (**COMPLETED - TESTED** - 2026-10-15)
- [x] **Milestone 4: Tracker HTTP Control Plane** (**COMPLETED - TESTED** - 2026-11-03)
- [x] **Milestone 5: Peer TCP Connection & Handshake Engine** (**COMPLETED - TESTED** - 2026-11-05)
- [x] **Milestone 6: Download Scheduler & Swarm Orchestration** (**COMPLETED - TESTED** - 2026-11-09)
- [x] **Milestone 7: End-to-End Swarm Integration & Seeder CLI** (**COMPLETED - TESTED** - 2026-11-17)
- [x] **Milestone 8: Client-Server Baseline & Performance Benchmarking** (**COMPLETED - TESTED** - 2026-11-20)

---

## Milestone Details

### Milestone 1: Project Foundation & Environment Setup (COMPLETED)
- **Goal:** Establish repo structure, pyproject configuration, requirements.txt, health endpoints, test runner, linting/typing setup, and core architecture docs.
- **Deliverables:**
  - `pyproject.toml` and `requirements.txt` with Python 3.12+, FastAPI, Uvicorn, pytest, Ruff, mypy, Matplotlib.
  - `src/p2p/` package hierarchy (`config.py`, `tracker/`, `peer/`, `protocol/`, `storage/`).
  - Minimal FastAPI Tracker `/health` endpoint.
  - Unit test suite proving test harness works (`tests/unit/test_health.py`, `tests/unit/test_config.py`).
  - Architecture, Protocol, Manifest, Testing, Benchmarking, and Implementation Plan documentation.
- **Acceptance Criteria (Verified):**
  - `pytest` runs and passes cleanly (4/4 passed in 1.28s).
  - `ruff check .` passes without lint errors.
  - `mypy src/p2p` passes without type errors.

---

### Milestone 2: Wire Framing Codec & Protocol Messages (COMPLETED)
- **Goal:** Implement pure length-prefixed framing and binary/JSON message encoders/decoders.
- **Deliverables:**
  - `src/p2p/protocol/codec.py` (`encode_frame`, `decode_frame`, `read_frame`, `write_frame`, `read_message`, `write_message`).
  - Data classes for `Handshake`, `Bitfield`, `Request`, `Piece`, `Have` messages in `src/p2p/protocol/messages.py`.
  - Frame reading bounds checking (`max_body`) *before* buffer allocation.
- **Acceptance Criteria (Verified):**
  - 99% test coverage for round-trip encoding and decoding of all 5 message types (53 passed tests).
  - Tests for truncated frames, split reads, merged reads, oversized length prefixes, malformed JSON, non-zero spare bitfield bits, timeouts, socket resets, and write locks.
  - `ruff check .`, `ruff format`, and `mypy` pass cleanly with zero warnings/errors.

---

### Milestone 3: Manifest Engine & Storage Integrity (COMPLETED - TESTED)
- **Goal:** File chunking, manifest JSON creation/validation, path traversal protection, SHA-256 validation, `.part` file writing, and atomic finalization.
- **Deliverables:**
  - `src/p2p/storage/manifest.py` (build manifest, validate schema, compute canonical Swarm ID).
  - `src/p2p/storage/manager.py` (safe target path resolution, chunk writer, SHA-256 chunk verifier, atomic finalize rename).
- **Acceptance Criteria:**
  - Manifest validator rejects malformed files, invalid counts, illegal chunk sizes, or invalid hex digests.
  - `validate_safe_filename()` blocks path traversal attempts (`..`), drive-letter and absolute paths, NUL bytes, and unsafe platform-specific names.
  - Corrupt chunks are rejected and not written to disk. Whole-file verification matches before `.part` -> final rename.
- **Verified implementation:** `manifest.py` builds, validates, loads, and atomically writes the v1 JSON schema; computes the canonical Swarm ID; caps input at 4 MiB and at 30,000 chunks. `manager.py` verifies each chunk before writing and verifies the on-disk file before atomic replacement. Empty files are rejected.
- **Verification:** `pytest` — 105 passed; `ruff check .` — passed; `mypy src/p2p` — passed (11 source files); targeted Ruff formatting check passed. Run on 2026-10-15 in the current working tree.

---

### Milestone 4: Tracker HTTP Control Plane
- **Goal:** Complete Tracker service with in-memory swarm registry, peer announcement processing, peer list sampling, and injectable clock for stale peer cleanup.
- **Deliverables:**
  - `src/p2p/tracker/registry.py` (SwarmRegistry with fake/monotonic clock injection).
  - `src/p2p/tracker/server.py` (FastAPI `/announce`, `/swarms/{swarm_id}/peers`, `/health`).
- **Acceptance Criteria:**
  - `POST /announce` registers peers, updates `last_seen`, returns active peer list excluding caller.
  - Inactive peers (`> 3 * heartbeat_interval`) are automatically evicted.
  - `GET /swarms/{swarm_id}/peers` returns validated, active peer details; a valid unknown swarm returns an empty list.
  - FastAPI integration tests use `httpx.AsyncClient` with `ASGITransport`.
- **Verified implementation:** Strict Pydantic request validation; synchronous in-memory registry with injectable monotonic clock and deterministic random sampling; start/heartbeat/completed/stopped semantics; stale-peer eviction and empty-swarm cleanup; FastAPI routes with dependency injection and 50-peer maximum.
- **Verification:** 116 Milestone 4 tests passed; Ruff lint/format and Mypy passed for the Milestone 4 files. Full-project verification details, including unrelated platform/type-check limitations, are recorded in `docs/project-status.md`.

---

### Milestone 5: Peer TCP Connection & Handshake Engine (COMPLETED - TESTED)
- **Goal:** Async TCP listener server and client connector managing connection lifecycle, handshake exchange, bitfield validation, and socket timeouts.
- **Deliverables:**
  - `src/p2p/peer/connection.py` (`PeerConnection` state machine wrapper over `StreamReader`/`StreamWriter`).
  - `src/p2p/peer/server.py` (`PeerServer` async TCP listener with connection tracking and graceful shutdown).
- **Acceptance Criteria (Verified):**
  - Successfully connects two loopback peers, validates handshakes, and exchanges bitfields.
  - Reject connections on mismatched version, wrong swarm ID, self-connection, or out-of-order protocol messages.
  - Timeouts enforced on connect, handshake, and idle/stall frame reads. Sockets closed cleanly without task leaks.
  - Bi-directional steady state transfers for `REQUEST`, `PIECE`, and `HAVE` with range checks and unsolicited piece rejection.
- **Verified implementation:** `PeerConnection` encapsulates connection states (`UNCONNECTED`, `AWAIT_HANDSHAKE`, `AWAIT_BITFIELD`, `STEADY_STATE`, `CLOSED`), serialized writes with `asyncio.Lock`, in-flight request bounding, and clean socket teardown. `PeerServer` handles ephemeral port binding, multiple concurrent clients, and cancellation cleanup.
- **Verification:** 32 Milestone 5 tests passed (26 unit, 6 integration) in 1.68s; full project suite 253 passed; Ruff lint, format, and Mypy passed cleanly on 2026-11-05.

---

### Milestone 6: Download Scheduler & Swarm Orchestration (COMPLETED - TESTED)
- **Goal:** Chunk selection policy, chunk reservation (`IN_FLIGHT`), parallel piece requests, retries across peers, HAVE broadcasts, and graceful cancellation.
- **Deliverables:**
  - `src/p2p/peer/scheduler.py` (DownloadScheduler for missing vs in-flight vs verified chunks).
  - `src/p2p/peer/downloader.py` (`DownloadWorker` and `SwarmDownloader`).
  - `tests/unit/test_scheduler.py` (scheduler, worker, bounds, retries, and cancellation coverage).
  - `tests/integration/test_downloader_loopback.py` (real TCP transfer, HAVE, failover, and cleanup coverage).
- **Acceptance criteria (verified):**
  - Seeded random selection among a peer's available missing chunks; reservations prevent duplicate in-flight work.
  - Concurrent downloads across connected peers, bounded by `MAX_PEER_CONNECTIONS` and `MAX_GLOBAL_INFLIGHT`; at most one request per peer is in flight.
  - Received `HAVE` updates peer availability. Verified stored chunks are broadcast with `HAVE` to other active peers.
  - Chunk length/hash failures, protocol failures, and disconnects release reservations; exhausted peers are retired so another peer can retry missing chunks.
  - Cancellation releases in-flight reservations, closes owned connections, and propagates `CancelledError`.
  - No available peer results in `NoAvailablePeersError`; complete downloads pass whole-file verification and atomic finalization.
- **Verification on 2026-11-09:** `.\.venv\Scripts\python.exe -m pytest -ra` — 273 passed (one upstream Starlette/httpx deprecation warning); the focused scheduler/downloader test command in `docs/testing.md` — 20 passed with 90% statement coverage for `downloader.py`; the five loopback tests passed in each of five consecutive runs. `ruff check .`, `ruff format --check src/p2p tests`, and `mypy src/p2p tests` passed. Exact commands/results are in `docs/project-status.md`.

---

### Milestone 7: End-to-End Swarm Integration & Seeder CLI (COMPLETED - TESTED, 2026-11-17)
- **Goal:** Connect the existing Tracker, peer TCP server/connection, verified storage, and downloader into complete seed/download lifecycles with a usable CLI and end-to-end validation.
- **Deliverables:**
  - `src/p2p/peer/client.py` (`SwarmPeer`): verified file serving, peer discovery, outbound connections, start/heartbeat/completed/stopped announcements, HAVE propagation, and cleanup.
  - `src/p2p/cli.py` and the `p2p` project script: `tracker-start`, `create-manifest`, `seed-file`, and `download-file`.
  - Bounded inbound connections in `PeerServer`; a peer's inbound and outbound connections share the `MAX_PEER_CONNECTIONS` limit.
  - `tests/unit/test_cli.py`, `tests/unit/test_swarm_peer.py`, and `tests/e2e/test_full_transfer.py`.
- **Acceptance criteria (verified):**
  - Seeder validates the local file against the manifest before announcing or serving; served chunks are checked against the manifest.
  - Peers announce `started`, periodically heartbeat at the tracker-provided interval, announce `completed` after final verification, and best-effort announce `stopped`.
  - Leechers discover from `/announce`, connect to live peers within the connection cap, use verified partial chunks for uploading, and process HAVE updates while waiting for other messages.
  - A full loopback transfer uses one tracker, one seeder, and three concurrent leechers; all outputs match the original bytes and SHA-256.
  - A staged regression transfer completes one leecher, stops the original seeder, and proves that a later leecher receives nonzero PIECE payload bytes from the completed leecher and verifies the reconstructed file.
  - Discovery tries later candidates after failures, filters duplicate and already-connected peers, and respects the combined inbound/outbound connection limit.
  - Cancelling a peer handshake or discovery closes sockets and awaits connector tasks; discovery cancellation restores the shared connection-capacity limit.
  - Startup rollback closes the HTTP client and signals stopped even if listener shutdown fails, while reporting both startup and cleanup errors.
  - Concurrent peer and connection close calls await shared cleanup; failed handshakes release inbound capacity; listener shutdown cancels and awaits active handlers before closing sockets and awaiting listener closure.
  - IPv4 remains supported and bracketed IPv6 literals are normalized for socket use when IPv6 is available.
  - Tracker lifecycle events, HAVE exchange, stopped peer removal, and heartbeat-task cleanup are asserted.
  - CLI exposes all four requested commands through both `p2p` and `python -m p2p.cli`.
- **Verification on 2026-11-17:** `.\.venv\Scripts\python.exe -m pytest -ra` — 304 passed; unit — 270 passed; integration — 32 passed; E2E — 2 passed. The no-peer CLI, startup rollback, and handshake/discovery cancellation regressions are covered. Ruff, source/test format check, Mypy, both CLI help entry points, and `git diff --check` passed. The interactive Windows smoke used a 1 MiB file and verified byte equality, matching SHA-256 (`042D84D3772B8CC9080A8F388C428C11D88F8566E5A38FDA322FC8EA33492CFC`), Ctrl+C exit for tracker/seeder/leecher, an empty tracker peer list, and no matching Python processes. This was one Windows run, not a repeated signal stress test or cross-platform test. See `docs/testing.md` for exact commands and `docs/project-status.md` for the verification log.

---

### Milestone 8: Client-Server Baseline & Performance Benchmarking
- **Goal:** Automated benchmark harness comparing P2P distribution against a Client-Server baseline under token-bucket rate limits.
- **Deliverables:**
  - [x] Client-server baseline peer option and CLI flag (tracker schema unchanged;
    [ADR 0006](adr/0006-download-only-baseline.md)).
  - [x] Shared token-bucket upload limits (`TokenBucketRateLimiter`, CLI `--upload-rate-limit`).
  - [x] Transfer metric counters (`bytes_uploaded`, `bytes_downloaded`, `total_retries`, `chunk_hash_failures`, duration, throughput).
  - [x] `bench/run_experiments.py` (N=1,2,4,8 sweep, warmups, seeded order, fresh resources, raw CSV).
  - [x] `bench/plot_results.py` (Headless charts, mean/sample SD, derived summary and trial audit).
- **Acceptance Criteria:**
  - Baseline clients verify downloads using the P2P transfer path while sending
    no chunk advertisements or PIECE payloads, including after completion.
  - Token-bucket upload rate limiter throttles aggregate peer uploading with deterministic clock support and safe cancellation.
  - Transfer metric counters record upload/download volumes, retry counts, integrity failures, and completion time per node.
  - Experiments run across varying client counts (e.g. 1, 2, 4, 8 clients) with 5 repetitions per config.
  - CSV dataset committed in `bench/results/` and plots generated in `bench/plots/`.
- **Current scope:** Baseline controls, upload rate limiting, transfer metrics,
  workload runner and plot analysis are implemented with correctness coverage.
  The full N=1,2,4,8 sweep ran with 5 measured repetitions plus 1 warmup per
  configuration: 48 trials, 180 verified client observations, CSV and four plots
  generated. The raw CSV is versioned alongside the runner, satisfying the
  dataset acceptance step; generated plots remain reproducible and ignored.
  See `docs/experiments.md` for results and exact commands, and
  `docs/project-status.md` for validation. Real-network/multi-process performance
  remains outside this loopback experiment.
