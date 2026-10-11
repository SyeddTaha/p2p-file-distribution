# Project Implementation Plan & Milestones

This document outlines the small, testable implementation milestones for the P2P File Distribution System. Each milestone contains explicit deliverables and acceptance criteria.

---

## Milestone Status Overview

- [x] **Milestone 1: Project Foundation & Environment Setup** (**COMPLETED** - 2026-10-10)
- [x] **Milestone 2: Wire Framing Codec & Protocol Messages** (**COMPLETED** - 2026-10-11)
- [ ] **Milestone 3: Manifest Engine & Storage Integrity** (PLANNED / NEXT UP)
- [ ] **Milestone 4: Tracker HTTP Control Plane** (PLANNED)
- [ ] **Milestone 5: Peer TCP Connection & Handshake Engine** (PLANNED)
- [ ] **Milestone 6: Download Scheduler & Swarm Orchestration** (PLANNED)
- [ ] **Milestone 7: End-to-End Swarm Integration & Seeder CLI** (PLANNED)
- [ ] **Milestone 8: Client-Server Baseline & Performance Benchmarking** (PLANNED)

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

### Milestone 3: Manifest Engine & Storage Integrity
- **Goal:** File chunking, manifest JSON creation/validation, path traversal protection, SHA-256 validation, `.part` file writing, and atomic finalization.
- **Deliverables:**
  - `src/p2p/storage/manifest.py` (build manifest, validate schema, compute canonical Swarm ID).
  - `src/p2p/storage/manager.py` (safe target path resolution, chunk writer, SHA-256 chunk verifier, atomic finalize rename).
- **Acceptance Criteria:**
  - Manifest validator rejects malformed files, invalid counts, illegal chunk sizes, or invalid hex digests.
  - `validate_safe_filename()` blocks path traversal attempts (`..`, drive letters, absolute paths, NUL bytes).
  - Corrupt chunks are rejected and not written to disk. Whole-file verification matches before `.part` -> final rename.

---

### Milestone 4: Tracker HTTP Control Plane
- **Goal:** Complete Tracker service with in-memory swarm registry, peer announcement processing, peer list sampling, and injectable clock for stale peer cleanup.
- **Deliverables:**
  - `src/p2p/tracker/registry.py` (SwarmRegistry with fake/monotonic clock injection).
  - `src/p2p/tracker/server.py` (FastAPI `/announce`, `/swarms/{swarm_id}/peers`, `/health`).
- **Acceptance Criteria:**
  - `POST /announce` registers peers, updates `last_seen`, returns active peer list excluding caller.
  - Inactive peers (`> 3 * heartbeat_interval`) are automatically evicted.
  - Full FastAPI `TestClient` integration test suite.

---

### Milestone 5: Peer TCP Connection & Handshake Engine
- **Goal:** Async TCP listener server and client connector managing connection lifecycle, handshake exchange, bitfield validation, and socket timeouts.
- **Deliverables:**
  - `src/p2p/peer/connection.py` (PeerConnection state machine wrapper over StreamReader/StreamWriter).
- **Acceptance Criteria:**
  - Successfully connects two loopback peers, validates handshakes, and exchanges bitfields.
  - Reject connections on mismatched version, wrong swarm ID, or out-of-order protocol messages.
  - Timeouts enforced on connect, handshake, and frame reads. Sockets closed cleanly without task leaks.

---

### Milestone 6: Download Scheduler & Swarm Orchestration
- **Goal:** Chunk selection policy, chunk reservation (`IN_FLIGHT`), parallel piece requests, retries across peers, HAVE broadcasts, and graceful cancellation.
- **Deliverables:**
  - `src/p2p/peer/scheduler.py` (DownloadScheduler for missing vs in-flight vs verified chunks).
  - `src/p2p/peer/downloader.py` (worker loop requesting pieces and passing to storage).
- **Acceptance Criteria:**
  - Parallel downloading across multiple peers without duplicate in-flight requests.
  - Slow or disconnecting peers release in-flight chunks for reassignment to another peer.
  - Received verified chunks trigger `HAVE` broadcasts to all connected peers.

---

### Milestone 7: End-to-End Swarm Integration & Seeder CLI
- **Goal:** CLI tools for seeding files, launching tracker, downloading files, and full end-to-end integration tests.
- **Deliverables:**
  - `src/p2p/cli.py` (`tracker-start`, `create-manifest`, `seed-file`, `download-file`).
  - End-to-end integration test suite (`tests/e2e/test_full_transfer.py`).
- **Acceptance Criteria:**
  - Full transfer test: 1 tracker + 1 seeder + 3 leechers download file concurrently on loopback.
  - Final reconstructed file SHA-256 matches original file bit-for-bit.

---

### Milestone 8: Client-Server Baseline & Performance Benchmarking
- **Goal:** Automated benchmark harness comparing P2P distribution against a Client-Server baseline under token-bucket rate limits.
- **Deliverables:**
  - Client-server baseline mode flag in peer/tracker code.
  - `bench/run_experiments.py` (Automated workload runner exporting CSV data).
  - `bench/plot_results.py` (Headless Matplotlib chart generator).
- **Acceptance Criteria:**
  - Experiments run across varying client counts (e.g. 1, 2, 4, 8 clients) with 5 repetitions per config.
  - CSV dataset committed in `bench/results/` and plots generated in `bench/plots/`.
