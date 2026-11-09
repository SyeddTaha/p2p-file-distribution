# Project Status & Team Workflow Tracking

> Last updated: 2026-11-09. Milestone 6 scheduler and bounded connected-peer orchestration are implemented and tested; Milestone 7 is next.

---

## 1. Project Phase & Milestone Summary

| Milestone | Description | Status | Active / Target Date | Verified Checks |
| :--- | :--- | :---: | :---: | :--- |
| **Milestone 1** | **Project Foundation & Tooling Setup** | **DONE** | 2026-10-10 | `pytest` (4/4 passed), `ruff` (clean), `mypy` (clean) |
| **Milestone 2** | **Wire Framing Codec & Messages** | **DONE** | 2026-10-11 | `pytest` (53/53 passed), `ruff` (clean), `mypy` (clean), 99% coverage |
| **Milestone 3** | **Manifest Engine & Storage Integrity** | **TESTED** | 2026-10-15 | Full `pytest` (105 passed), `ruff check .`, `mypy src/p2p`, targeted format check passed |
| **Milestone 4** | **Tracker HTTP Control Plane** | **TESTED** | 2026-11-03 | 116 Milestone 4 tests passed; targeted Ruff, formatting, and Mypy passed |
| **Milestone 5** | **Peer TCP Connection Engine** | **TESTED** | 2026-11-05 | 32 Milestone 5 tests passed (26 unit, 6 integration), full suite 253 passed, Ruff and Mypy clean |
| **Milestone 6** | **Download Scheduler & Orchestrator** | **TESTED** | 2026-11-09 | Full suite 273 passed; 20 focused tests, 90% downloader coverage; 5 loopback tests passed in 5 consecutive runs |
| **Milestone 7** | **End-to-End Swarm & Seeder CLI** | PLANNED | To Do | Full multi-peer loopback file distribution E2E tests |
| **Milestone 8** | **Benchmarking & Baseline Mode** | PLANNED | To Do | Client-Server vs P2P comparison, CSV dataset, plots |

---

## 2. Teammate Environment Setup

Teammates joining the project can initialize their environment with one command block:

```bash
# 1. Clone repository & enter directory
git clone <repo-url>
cd p2p-file-distribution

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1    # On Windows (PowerShell)
source .venv/bin/activate     # On Linux / macOS

# 3. Install dependencies and project in editable mode
pip install -r requirements.txt

# 4. Verify environment setup
pytest
ruff check .
mypy src/p2p
```

---

## 3. Feature Status Table

| Area | Feature | State | Tests run? | Notes / Verification Command |
|---|---|---|---|---|
| Foundation | Package layout & pyproject.toml | **Tested** | Yes | `pytest`, `ruff check .`, `mypy src/p2p` passed |
| Foundation | `requirements.txt` environment setup | **Tested** | Yes | Verified dependency locking & installation |
| Protocol | Frame codec (length-prefixed) | **Tested** | Yes | `read_frame`/`write_frame`, bounds check before allocation |
| Protocol | HANDSHAKE | **Tested** | Yes | JSON object parsing, version 1, 64-hex swarm ID, port 1..65535 |
| Protocol | BITFIELD | **Tested** | Yes | Bitmask queries, spare bit zero-check, length check |
| Protocol | REQUEST / PIECE | **Tested** | Yes | Bounds checks, MAX_CHUNK_SIZE safety limits |
| Protocol | HAVE | **Tested** | Yes | uint32 chunk index broadcast validation |
| Protocol | Timeouts and malformed-input handling | **Tested** | Yes | Idle/stall timeouts, split/merged reads, connection reset |
| Manifest | Manifest creation & JSON schema | **Tested** | Yes | `build_manifest`, `load_manifest`, `write_manifest`; v1 schema and bounded JSON validation |
| Manifest | Manifest validation & Swarm ID | **Tested** | Yes | Strict field/count/size/hash validation; canonical JSON SHA-256 |
| Storage | Chunk verification (length + SHA-256) | **Tested** | Yes | Invalid index, length, and digest rejected before write; duplicate accepted index is not overwritten |
| Storage | Safe paths and `.part` temp files | **Tested** | Yes | Traversal, absolute/drive paths, separators, NUL, overlong names, and symlink destinations rejected |
| Storage | Final file verification and atomic finalize | **Tested** | Yes | Incomplete/mismatched files are not published; valid `.part` atomically replaced |
| Tracker | Basic Health Endpoint | **Tested** | Yes | Verified via `tests/unit/test_health.py`; response remains unchanged |
| Tracker | Request models and announce validation | **Tested** | Yes | Strict IDs, hosts, ports, seeder flag, events, and unknown-field rejection |
| Tracker | Peer registration / announce | **Tested** | Yes | Started, heartbeat (including re-registration after tracker restart), completed, stopped; peer exclusion and 50-peer cap |
| Tracker | Heartbeat and stale-peer expiry | **Tested** | Yes | Injectable monotonic clock; expiry is strictly older than 90 seconds; lazy and explicit cleanup |
| Tracker | Peer-list and health HTTP API | **Tested** | Yes | ASGI integration tests cover response schemas, valid unknown swarms, malformed swarm IDs, and dependency overrides |
| Peer | TCP Connection & State Machine | **Tested** | Yes | `PeerConnection` states (`UNCONNECTED` to `CLOSED`), version/swarm checks, timeouts, socket teardown |
| Peer | Async TCP Server / Client Connector | **Tested** | Yes | `PeerServer` ephemeral binding, concurrent client tracking, graceful shutdown |
| Peer | Handshake & Bitfield exchange | **Tested** | Yes | Bi-directional exchange, spare bit verification, self-connection rejection |
| Peer | Steady-state message transfer | **Tested** | Yes | `REQUEST`, `PIECE`, `HAVE` with range checks and unsolicited piece rejection |
| Peer | Seeding (serving verified chunks) | Planned | No | Milestone 7 CLI / worker integration |
| Peer | Scheduler and connected-peer download orchestration | **Tested** | Yes | Bounded parallel peer requests, synchronous reservations, storage verification, failover, HAVE updates, and cancellation cleanup |
| Peer | Download completion and no-peer failure | **Tested** | Yes | `StorageManager.finalize()` verifies/publishes complete files; `NoAvailablePeersError` is raised for unresolved chunks |
| Testing | Unit & integration tests | **Tested** | Yes | Latest full suite: 273 passed; focused scheduler/downloader tests: 20 passed, 90% statement coverage for `downloader.py`; loopback tests repeated 5 times |
| Benchmarking | Baseline mode & runner | Planned | No | Milestone 8 |

---

## 4. Documentation Status

| Document | State | Purpose |
|---|---|---|
| `README.md` | Updated | Quick start, stack, project overview, active milestones |
| `AGENTS.md` | Updated | Shared AI rules & all 12 project/ecosystem skills |
| `requirements.txt` | Created | Team dependency requirements file |
| `docs/architecture.md` | Created | Components, state ownership, sequence diagrams |
| `docs/protocol.md` | Created | Wire format specification, message codes, state machine |
| `docs/manifest-format.md` | Updated | JSON schema, limits, Swarm ID, safe paths, storage workflow |
| `docs/manifest.md` | Created | Linked summary |
| `docs/implementation-plan.md` | Updated | Milestones 1-6 tested; Milestone 7 is next |
| `docs/testing.md` | Updated | Scenario matrix and verified Milestone 6 unit/integration coverage |
| `docs/adr/0004-download-scheduling-and-failover.md` | Created | Seeded selection, per-peer concurrency, retry, and failover policy |
| `docs/experiments.md` | Created | Hypotheses, control variables, CSV format |
| `docs/adr/0001-project-structure-and-stack.md` | Created | Stack & directory layout |
| `docs/adr/0002-wire-protocol-framing-and-limits.md` | Created | Framing format & security bounds |
| `docs/adr/0003-manifest-v1-and-storage-policy.md` | Created | Manifest v1, empty-file and storage policies |
| `docs/project-status.md` | Updated | Milestone 6 tested state, current verification, and Milestone 7 boundary |

---

## 5. Test and Benchmark Log

| Date | Commit | Command | Result |
|---|---|---|---|
| 2026-10-10 | Initial setup | `.\.venv\Scripts\pytest` | **Passed** (4 passed in 1.28s) |
| 2026-10-10 | Initial setup | `.\.venv\Scripts\ruff check .` | **Passed** (All checks passed) |
| 2026-10-10 | Initial setup | `.\.venv\Scripts\mypy src/p2p` | **Passed** (No issues found in 7 source files) |
| 2026-10-11 | Milestone 2 | `.\.venv\Scripts\pytest -v` | **Passed** (53 passed in 1.44s) |
| 2026-10-11 | Milestone 2 | `.\.venv\Scripts\ruff check .` | **Passed** (All checks passed) |
| 2026-10-11 | Milestone 2 | `.\.venv\Scripts\mypy src/p2p tests` | **Passed** (No issues found in 16 source files) |
| 2026-10-11 | Milestone 2 | `.\.venv\Scripts\pytest --cov=src/p2p/protocol` | **Passed** (99% coverage on protocol package) |
| 2026-10-15 | Milestone 3 (worktree based on `81a6a23`) | `.\.venv\Scripts\python.exe -m pytest` | **Passed** (105 passed; one Starlette/httpx deprecation warning) |
| 2026-10-15 | Milestone 3 (worktree based on `81a6a23`) | `.\.venv\Scripts\ruff.exe check .` | **Passed** (All checks passed) |
| 2026-10-15 | Milestone 3 (worktree based on `81a6a23`) | `.\.venv\Scripts\mypy.exe src\p2p` | **Passed** (No issues found in 11 source files) |
| 2026-10-15 | Milestone 3 (worktree based on `81a6a23`) | `.\.venv\Scripts\ruff.exe format --check src\p2p\protocol src\p2p\storage tests\unit\test_protocol.py tests\unit\test_storage.py` | **Passed** (8 files already formatted) |
| 2026-11-03 | Milestone 4 (current worktree) | `.\.venv\Scripts\python.exe -m pytest tests\unit\test_tracker_registry.py tests\integration\test_tracker_api.py` | **Passed** (116 passed) |
| 2026-11-03 | Milestone 4 (current worktree) | `.\.venv\Scripts\ruff.exe check src\p2p\tracker\models.py src\p2p\tracker\registry.py src\p2p\tracker\server.py tests\helpers\clock.py tests\unit\test_tracker_registry.py tests\integration\test_tracker_api.py` | **Passed** (All checks passed) |
| 2026-11-03 | Milestone 4 (current worktree) | `.\.venv\Scripts\ruff.exe format --check src\p2p\tracker\models.py src\p2p\tracker\registry.py src\p2p\tracker\server.py tests\helpers\clock.py tests\unit\test_tracker_registry.py tests\integration\test_tracker_api.py` | **Passed** (6 files already formatted) |
| 2026-11-03 | Milestone 4 (current worktree) | `.\.venv\Scripts\mypy.exe src\p2p\tracker\models.py src\p2p\tracker\registry.py src\p2p\tracker\server.py tests\helpers\clock.py tests\unit\test_tracker_registry.py tests\integration\test_tracker_api.py` | **Passed** (No issues found in 6 source files) |
| 2026-11-05 | Milestone 5 | `.\.venv\Scripts\python.exe -m pytest tests\unit\test_peer_connection.py tests\integration\test_peer_loopback.py --cov=src/p2p/peer -v` | **Passed** (32 passed in 2.49s, 80% coverage on `src/p2p/peer`) |
| 2026-11-05 | Full project | `.\.venv\Scripts\python.exe -m pytest` | **Passed** (253 passed, 1 Starlette deprecation warning) |
| 2026-11-05 | Full project | `.\.venv\Scripts\ruff.exe check .` | **Passed** (All checks passed) |
| 2026-11-05 | Full project | `.\.venv\Scripts\ruff.exe format --check src/p2p tests` | **Passed** (29 files already formatted) |
| 2026-11-05 | Full project | `.\.venv\Scripts\mypy.exe src\p2p tests` | **Passed** (No issues found in 29 source files) |
| 2026-11-09 | Milestone 6 | `.\.venv\Scripts\python.exe -m pytest tests\unit\test_scheduler.py tests\integration\test_downloader_loopback.py --cov=p2p.peer.downloader --cov-report=term-missing -ra` | **Passed** (20 passed; `downloader.py` 90% statement coverage) |
| 2026-11-09 | Milestone 6 stability | `.\.venv\Scripts\python.exe -m pytest tests\integration\test_downloader_loopback.py -q` (5 consecutive runs) | **Passed** (5 tests per run; 25 total test executions) |
| 2026-11-09 | Full project | `.\.venv\Scripts\python.exe -m pytest -ra` | **Passed** (273 passed; one upstream Starlette/httpx deprecation warning) |
| 2026-11-09 | Full project | `.\.venv\Scripts\python.exe -m ruff check .` | **Passed** (All checks passed) |
| 2026-11-09 | Full project | `.\.venv\Scripts\python.exe -m ruff format --check src/p2p tests` | **Passed** (33 files already formatted) |
| 2026-11-09 | Full project | `.\.venv\Scripts\python.exe -m mypy src/p2p tests` | **Passed** (No issues found in 33 source files) |

## 6. Open Issues & Known Limitations

- Milestone 3 storage operations are synchronous; async callers must offload large file work and serialize access to a shared `StorageManager`.
- Full test runs emit one upstream Starlette/httpx deprecation warning; it does not fail tests.
- Milestone 6 accepts already-connected peers; tracker-driven discovery, CLI operations, and a complete tracker-plus-multiple-leecher transfer remain Milestone 7 scope.
- Each peer worker currently has one outstanding request at a time; per-peer pipelining is not implemented.

## 7. Decisions Needed

- No outstanding Milestone 6 decisions. Milestone 7 must integrate tracker discovery and provide the complete CLI/E2E workflow.
