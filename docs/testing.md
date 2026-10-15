# Testing Strategy & Guide

## 1. Overview & Principles

Testing network applications requires strict isolation, determinism, and clean resource cleanup.

- **No External Network Dependencies:** All network tests bind exclusively to loopback (`127.0.0.1`) on ephemeral port `0`.
- **Deterministic Experiments:** Random number generators are explicitly seeded. Time-dependent logic (stale peer expiry, heartbeats) uses an **injectable clock interface** rather than real-world wall clock sleeps.
- **Isolated Filesystem Work:** All file writes occur within pytest `tmp_path` temporary directories.
- **Strict Cleanup:** Every async test must close sockets, stop server instances, and await background tasks before finishing.

---

## 2. Test Pyramid & Conventions

```
                  / \
                 /   \
                / E2E \       <-- Full Tracker + Multi-Peer Loopback Swarms
               /-------\
              / Integr. \     <-- Socket Handshake, Bitfield Exchange, Tracker Endpoints
             /-----------\
            /  Unit Tests \   <-- Codec, Manifest Validation, Scheduler, Path Safety
           /---------------\
```

### Async Test Framework
- Test runner: `pytest` with `pytest-asyncio`.
- Configuration in `pyproject.toml`: `asyncio_mode = "auto"`.

---

## 3. Scenario Matrix

| Area | Component / Feature | Test Scenarios |
|---|---|---|
| **Protocol Codec** | Message Encoding / Decoding | Round-trip serialization for Handshake, Bitfield, Request, Piece, Have. |
| **Protocol Framing** | Stream Boundaries & Safety | Split frame delivery, merged frames in single read, oversized length prefix protection, truncated header/body. |
| **Manifest & Storage** | JSON Manifest Parsing | Build/load/write manifests and canonical Swarm ID; reject malformed fields/JSON, duplicate keys, empty files, invalid chunk counts/sizes, and invalid SHA-256 digests. |
| **Manifest & Storage** | Path Safety | `validate_safe_filename()` blocks traversal, absolute/drive paths, separators, NUL, overlong names, Windows reserved names, trailing dot/space, and symbolic-link destinations. |
| **Storage & Integrity** | Chunk Writing & Verification | Verify index/length/hash before write; ignore verified duplicates; cover one-byte, single-chunk, exact-multiple, and remainder sizes; reject incomplete/corrupted files; preserve `.part` on whole-file mismatch; atomically finalize valid files. |
| **Tracker Service** | Peer Announcements | `POST /announce` (`started`, `heartbeat`, `completed`, `stopped`), return peer list excluding self. |
| **Tracker Service** | Stale Peer Expiry | Inactive peer evicted after `3 * heartbeat_interval` using fake clock step. |
| **Peer Connection** | TCP Handshake Engine | Valid handshake exchange, version mismatch rejection, wrong swarm ID rejection, unsolicited piece rejection. |
| **Download Scheduler** | Chunk Reservation | `IN_FLIGHT` reservation prevention of duplicate requests across tasks, peer failure release of chunks. |
| **End-to-End** | Multi-Peer File Transfer | Tracker + Seeder + 3 Leechers downloading 1 MB file; bit-for-bit SHA-256 verification of output. |

---

## 4. Running the Tests

Execute the following commands from the repository root:

```bash
# Run full test suite
pytest

# Run with verbose output
pytest -v

# Run specific test category
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/

# Run with coverage report
pytest --cov=src/p2p
```
