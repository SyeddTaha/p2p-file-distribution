# Project Status & Team Workflow Tracking

> Last updated: 2026-11-17. Milestones 1-7 are implemented and tested; Milestone 8 remains planned.

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
| **Milestone 7** | **End-to-End Swarm & Seeder CLI** | **TESTED** | 2026-11-17 | Full suite 304 passed; staged leecher-to-leecher PIECE transfer; targeted startup/CLI/cancellation regressions; interactive Windows transfer, integrity, shutdown, deregistration, and process-cleanup smoke passed |
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
| Peer | Async TCP Server / Client Connector | **Tested** | Yes | `PeerServer` ephemeral binding and concurrent client tracking; active-connection shutdown cancels and awaits handlers, closes sockets, then waits for listener closure |
| Peer | Handshake & Bitfield exchange | **Tested** | Yes | Bi-directional exchange, spare bit verification, self-connection rejection |
| Peer | Steady-state message transfer | **Tested** | Yes | `REQUEST`, `PIECE`, `HAVE` with range checks and unsolicited piece rejection |
| Peer | Seeding (serving verified chunks) | **Tested** | Yes | Seeder source is checked against the manifest; only locally verified chunks are served and rehashed before sending |
| Peer | Scheduler and connected-peer download orchestration | **Tested** | Yes | Bounded parallel peer requests, synchronous reservations, storage verification, failover, HAVE updates, and cancellation cleanup |
| Peer | Download completion and no-peer failure | **Tested** | Yes | `StorageManager.finalize()` verifies/publishes complete files; `NoAvailablePeersError` is raised for unresolved chunks |
| Peer | Tracker-connected `SwarmPeer` lifecycle | **Tested** | Yes | Started, periodic heartbeat, completed, stopped; startup rollback closes HTTP resources and signals stopped even when server shutdown fails; discovery cancellation closes attempts and restores capacity |
| CLI | Tracker, manifest, seeder, and downloader commands | **Tested** | Yes | Editable install succeeded; both help entry points verified; invalid inputs and no-peer downloads report nonzero exit codes without tracebacks |
| End-to-end | Tracker-driven multi-leecher transfer | **Tested** | Yes | In-process FastAPI tracker and real loopback TCP; concurrent and staged relay tests verify a completed leecher serves actual nonzero PIECE bytes to a later leecher after the origin stops |
| Testing | Unit, integration, and E2E tests | **Tested** | Yes | Latest full suite: 304 passed; unit: 270 passed; integration: 32 passed; E2E: 2 passed; earlier shutdown and E2E regressions repeated 5 times |
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
| `docs/implementation-plan.md` | Updated | Milestone 7 acceptance and verification; Milestone 8 remains planned |
| `docs/testing.md` | Updated | Scenario matrix and Milestone 7 test commands/results |
| `docs/cli.md` | Created | Tracker, manifest, seeder, and downloader CLI reference |
| `docs/adr/0004-download-scheduling-and-failover.md` | Created | Seeded selection, per-peer concurrency, retry, and failover policy |
| `docs/adr/0005-integrated-swarm-peer-lifecycle.md` | Created | Tracker/peer lifecycle and per-connection message-reader ownership |
| `docs/experiments.md` | Created | Hypotheses, control variables, CSV format |
| `docs/adr/0001-project-structure-and-stack.md` | Created | Stack & directory layout |
| `docs/adr/0002-wire-protocol-framing-and-limits.md` | Created | Framing format & security bounds |
| `docs/adr/0003-manifest-v1-and-storage-policy.md` | Created | Manifest v1, empty-file and storage policies |
| `docs/project-status.md` | Updated | Current Milestone 7 verification, benchmark state, and known limitations |

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
| 2026-11-09 | Milestone 7 | `.\.venv\Scripts\python.exe -m pytest tests\unit\test_cli.py tests\unit\test_swarm_peer.py tests\integration\test_peer_loopback.py tests\integration\test_downloader_loopback.py tests\unit\test_scheduler.py tests\e2e\test_full_transfer.py -q` | **Passed** (38 passed) |
| 2026-11-09 | Milestone 7 | `.\.venv\Scripts\python.exe -m pytest -ra` | **Passed** (285 passed; one upstream Starlette/httpx deprecation warning) |
| 2026-11-09 | Milestone 7 | `.\.venv\Scripts\python.exe -m ruff check .` | **Passed** (All checks passed) |
| 2026-11-09 | Milestone 7 | `.\.venv\Scripts\python.exe -m ruff format --check src/p2p tests` | **Passed** (38 files already formatted) |
| 2026-11-09 | Milestone 7 | `.\.venv\Scripts\python.exe -m mypy src/p2p tests` | **Passed** (No issues found in 38 source files) |
| 2026-11-17 | Milestone 7 audit | `.\.venv\Scripts\python.exe -m pytest` | **Passed** (300 passed; one upstream Starlette/httpx deprecation warning) |
| 2026-11-17 | Milestone 7 audit | `.\.venv\Scripts\python.exe -m pytest tests\unit` | **Passed** (266 passed; one upstream Starlette/httpx deprecation warning) |
| 2026-11-17 | Milestone 7 audit | `.\.venv\Scripts\python.exe -m pytest tests\integration` | **Passed** (32 passed) |
| 2026-11-17 | Milestone 7 audit | `.\.venv\Scripts\python.exe -m pytest tests\e2e` | **Passed** (2 passed) |
| 2026-11-17 | Milestone 7 audit | `.\.venv\Scripts\python.exe -m pytest tests\integration\test_peer_loopback.py::test_server_shutdown_closes_active_connections_and_handler_tasks tests\e2e --tb=short -q` (5 consecutive runs) | **Passed** (3 tests per run; 15 total executions) |
| 2026-11-17 | Milestone 7 audit | `.\.venv\Scripts\python.exe -m ruff check .` | **Passed** (All checks passed) |
| 2026-11-17 | Milestone 7 audit | `.\.venv\Scripts\python.exe -m ruff format --check src\p2p tests` | **Passed** (38 files already formatted) |
| 2026-11-17 | Milestone 7 audit | `.\.venv\Scripts\python.exe -m mypy src\p2p tests` | **Passed** (No issues found in 38 source files) |
| 2026-11-17 | Milestone 7 audit | `.\.venv\Scripts\python.exe -m ruff format --check .` | **Not clean** (Ruff would reformat 17 Markdown files containing fenced examples; the documented source-and-test check passes) |
| 2026-11-17 | Milestone 7 targeted fixes | `.\.venv\Scripts\python.exe -m pytest -ra` | **Passed** (304 passed; one upstream Starlette/httpx deprecation warning) |
| 2026-11-17 | Milestone 7 targeted fixes | `.\.venv\Scripts\python.exe -m pytest tests\unit -o addopts='' -q` | **Passed** (270 passed; one upstream Starlette/httpx deprecation warning) |
| 2026-11-17 | Milestone 7 targeted fixes | `.\.venv\Scripts\python.exe -m pytest tests\unit\test_cli.py -q` | **Passed** (9 passed) |
| 2026-11-17 | Milestone 7 targeted fixes | `.\.venv\Scripts\python.exe -m pytest tests\e2e\test_full_transfer.py -q` | **Passed** (2 passed) |
| 2026-11-17 | Milestone 7 targeted fixes | `.\.venv\Scripts\python.exe -m ruff check .` | **Passed** (All checks passed) |
| 2026-11-17 | Milestone 7 targeted fixes | `.\.venv\Scripts\python.exe -m ruff format --check src\p2p tests` | **Passed** (38 files already formatted) |
| 2026-11-17 | Milestone 7 targeted fixes | `.\.venv\Scripts\python.exe -m mypy src\p2p tests` | **Passed** (No issues found in 38 source files) |
| 2026-11-17 | Milestone 7 targeted fixes | `git diff --check` | **Passed** |
| 2026-11-17 | CLI | `.\.venv\Scripts\python.exe -m pip install -e .` | **Passed** (editable package built and installed; setuptools emitted a license-table deprecation warning) |
| 2026-11-17 | CLI | `.\.venv\Scripts\python.exe -m p2p.cli --help`; `.\.venv\Scripts\p2p.exe --help` | **Passed** (both entry points listed all four commands) |
| 2026-11-17 | Local multi-process smoke | `python -m p2p.cli` tracker, seeder, and downloader processes | **Transfer passed** (20,080 bytes matched and SHA-256 verified); graceful Ctrl+C/Break shutdown was not verifiable in that run |
| 2026-11-17 | Interactive Windows M7 smoke | `python -m p2p.cli create-manifest`, `tracker-start`, `seed-file`, and `download-file` in separate PowerShell terminals | **Passed** (1,048,576 bytes; byte-for-byte equality; matching SHA-256 `042D84D3772B8CC9080A8F388C428C11D88F8566E5A38FDA322FC8EA33492CFC`; all three processes returned after Ctrl+C) |
| 2026-11-17 | Interactive Windows M7 smoke | `Invoke-RestMethod http://127.0.0.1:8000/swarms/ef3fbb61b390ba263b2503a97cb07209033d88f6b2df69f94af3ec3ca3135385/peers`; scoped `Get-CimInstance Win32_Process` check | **Passed** (empty peer list; no matching smoke-test Python processes remained) |

## 6. Open Issues & Known Limitations

- Milestone 3 storage operations are synchronous; async callers must offload large file work and serialize access to a shared `StorageManager`.
- Full test runs emit one upstream Starlette/httpx deprecation warning; it does not fail tests.
- Automated E2E tests use an in-process tracker. The single interactive Windows smoke run verified Ctrl+C shutdown and stopped-event deregistration for one tracker, seeder, and leecher; repeated signal stress and other operating systems were not exercised.
- A repository-wide `ruff format --check` flags 17 Markdown files with fenced examples in `.agents/skills/` and `docs/manifest-format.md`; the documented source-and-test command (`ruff format --check src/p2p tests`) passes.
- Each peer worker currently has one outstanding request at a time; per-peer pipelining is not implemented.

## 7. Decisions Needed

- No outstanding Milestone 7 decisions. Milestone 8 benchmarking is next.
