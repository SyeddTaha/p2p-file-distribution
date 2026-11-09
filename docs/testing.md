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
                / E2E \       <-- Full Tracker + Multi-Peer Loopback Swarms (Milestone 7)
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
| **Tracker Service** | Peer Announcements | `POST /announce` schema and event validation, unknown-field rejection, idempotency, peer exclusion, and the 50-peer response cap. |
| **Tracker Service** | Peer Names & Hosts | RFC 1123 label/hostname length edges, optional trailing dot, IPv4/IPv6, and invalid hostname syntax. |
| **Tracker Service** | Stale Peer Expiry | Fake-clock boundary at exactly 90 seconds and just beyond; eviction during announce/listing and empty-swarm cleanup. |
| **Tracker Service** | HTTP Peer Listing | `GET /swarms/{swarm_id}/peers` response fields, malformed ID rejection, unknown valid swarm response, and registry dependency isolation. |
| **Peer Connection** | TCP Handshake Engine | Valid handshake exchange, version mismatch rejection, wrong swarm ID rejection, unsolicited piece rejection. |
| **Download Scheduler** | Chunk Reservation | `IN_FLIGHT` reservation prevention of duplicate requests across tasks, peer failure release of chunks. |
| **Download Worker** | Async Fetch / Retry Flow | Unit tests cover storage-verified chunks, retries, retained reservations during retries, retry exhaustion, HAVE updates while awaiting PIECE, unexpected REQUEST, cancellation, and completion tracking. |
| **Swarm Downloader** | Multi-Peer Orchestration | Loopback tests cover concurrent peer requests, storage finalization, HAVE broadcasts, corrupt-peer and disconnect failover, no available chunks, and cancellation cleanup. |
| **End-to-End (Milestone 7)** | Tracker-Driven File Transfer | Full tracker + seeder + multiple leechers and CLI workflow; not implemented in Milestone 6. |

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

# Measure downloader module coverage across unit and loopback tests
pytest tests/unit/test_scheduler.py tests/integration/test_downloader_loopback.py --cov=p2p.peer.downloader --cov-report=term-missing -ra
```

### Milestone 6 verification

On 2026-11-09 the focused command above passed 20 tests and measured 90%
statement coverage for `src/p2p/peer/downloader.py`. Its unexecuted statements
are defensive validation branches and exceptional fallback paths; the
milestone's functional flows are additionally exercised over loopback. Full
tracker-driven E2E/CLI coverage belongs to Milestone 7.

The loopback downloader integration tests were run five consecutive times on
2026-11-09, with all five tests passing in every run. To repeat that stability
check in PowerShell:

```powershell
for ($i = 1; $i -le 5; $i++) {
    .\.venv\Scripts\python.exe -m pytest tests\integration\test_downloader_loopback.py -q
    if ($LASTEXITCODE -ne 0) { throw "Loopback test run $i failed" }
}
```
