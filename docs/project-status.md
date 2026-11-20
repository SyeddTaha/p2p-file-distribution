# Project Status & Team Workflow Tracking

> Last updated: 2026-11-20. Milestones 1-8 are implemented and tested. Milestone 8's full default loopback sweep ran: 48 trials, 180 verified client observations, raw CSV and plots generated. The implementation and raw dataset are versioned together on `feat/download-only-baseline`.

The optional local console on `feat/local-web-console` is **Tested** through API,
separate-process HTTP/TCP scenarios and the redesigned browser workflows. See
[web UI](web-ui.md), [design system](../DESIGN.md), and
[ADR 0009](adr/0009-local-web-console.md).

The documentation-only [complete handbook](P2P_COMPLETE_PROJECT_HANDBOOK.md) and
three companion guides are **Implemented** and source-checked at `121b31f`.
The fresh audit passed 390 pytest cases and eight isolated three-console API
rehearsal groups. Its two fresh browser runs stopped on the same stale-payload
DOM assertion after four groups; the 13-group results below are historical,
not a current rerun result. See the [coverage/evidence checklist](P2P_HANDBOOK_COVERAGE_CHECKLIST.md)
for exact commands, the polling synchronization gap, occupied-port fallback,
Mermaid rendering limitation and verified Notion publication. No production,
frontend, test, dependency or raw benchmark file changed in the handbook task.

The user-approved reference-led frontend redesign is **Tested**. The latest full
suite passed 390 tests with one existing upstream warning; the browser harness
passed 13 workflow groups, including real transfers, baseline, relay, keyboard
focus, responsive layouts and offline/recovery states. Ruff, formatting, mypy
and JS syntax passed. Python code and existing tests are unchanged. See the
[verification record](frontend-redesign-verification.md),
[design system](../DESIGN_SYSTEM.md), [pre-edit audit](frontend-redesign-audit.md)
and [approved plan](frontend-redesign-plan.md) for scope, checkpoints and limits.

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
| **Milestone 8** | **Benchmarking & Baseline Mode** | **Tested** | 2026-11-20 | 376 tests passed; Ruff/format/Mypy clean; full 48-trial loopback sweep, versioned raw CSV and four plots generated |

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
| Web console | Reference-led frontend visual and usability redesign | **Tested** | Yes | 13 Chrome workflow groups passed; five viewport widths, keyboard/focus, live data and failure/recovery; see redesign verification |
| Web console | Four-section local FastAPI/HTML/CSS/JS UI | **Tested** | Yes | Existing 390-test suite plus real browser transfer/import/export, relay, baseline and rate-cap coverage; accessibility/platform limits recorded |
| Instrumentation | Live copied peer snapshots and tracker swarm listing | **Tested** | Yes | Exact verified progress, final integrity state, source contributions, observed connections and fake-clock expiry |
| Web console | Recorded N=1,2,4,8 benchmark display | **Tested** | Yes | Existing CSV, shared pure analysis, eight summary rows and 48-trial audit; no new measured sweep |
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
| Testing | Unit, integration, and E2E tests | **Tested** | Yes | Latest full suite: 390 passed (2026-11-20); one upstream Starlette/httpx warning; redesign browser check separately passed 13 workflow groups |
| Benchmarking | Download-only baseline controls | **Tested** | Yes | `SwarmPeer(upload_enabled=False)` / `download-file --no-upload`; three concurrent clients receive only origin payloads; partial and complete clients refuse uploads |
| Benchmarking | Shared token-bucket upload rate limiter | **Tested** | Yes | `TokenBucketRateLimiter`, `SwarmPeer(upload_rate_limit=...)`, CLI `--upload-rate-limit`; deterministic clock, burst, cancellation safety; 28 unit tests |
| Benchmarking | Transfer metric counters | **Tested** | Yes | `bytes_uploaded`, `bytes_downloaded`, `total_retries`, `chunk_hash_failures`, duration, throughput on `SwarmDownloader` and `SwarmPeer`; full suite 343 passed |
| Benchmarking | Workload runner & plots | **Tested** | Yes | N=1,2,4,8 loopback transfer sweep; CLI/config validation, CSV/schema, aggregation and exclusion tests; smoke passed; final verification below |
| Benchmarking | Default workload dataset | **Tested** | Yes | **Run**: full 10 MiB sweep, 48 trials/180 verified client rows; [versioned raw data](../bench/results/experiments.csv), [results and limits](experiments.md) |

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
| `docs/implementation-plan.md` | Updated | Milestones 1-8 implementation and verification; raw CSV versioned with the runner |
| `docs/testing.md` | Updated | Scenario matrix, baseline correctness coverage, and validation commands/results |
| `docs/cli.md` | Created | Tracker, manifest, seeder, and downloader CLI reference |
| `docs/adr/0004-download-scheduling-and-failover.md` | Created | Seeded selection, per-peer concurrency, retry, and failover policy |
| `docs/adr/0005-integrated-swarm-peer-lifecycle.md` | Created | Tracker/peer lifecycle and per-connection message-reader ownership |
| `docs/adr/0006-download-only-baseline.md` | Created | Per-peer baseline policy, advertisement suppression, unchanged tracker schema |
| `docs/adr/0007-token-bucket-rate-limiting.md` | Created | Shared per-uploader bandwidth limit, burst handling, deterministic clock, safe cancellation |
| `docs/experiments.md` | Updated | Hypotheses, controls, runner commands, current CSV fields, exclusions and measurement limitations |
| `docs/adr/0008-in-process-benchmark-runner.md` | Created | Isolated ASGI tracker/loopback trials, seeded client schedules, observation and exclusion policy |
| `docs/adr/0001-project-structure-and-stack.md` | Created | Stack & directory layout |
| `docs/adr/0002-wire-protocol-framing-and-limits.md` | Created | Framing format & security bounds |
| `docs/adr/0003-manifest-v1-and-storage-policy.md` | Created | Manifest v1, empty-file and storage policies |
| `docs/project-status.md` | Updated | Current validation, measured loopback benchmark state and known limitations |
| `docs/course-report.md` | Created | Course narrative, four measured figures, tables, reliability evidence and limits; snapshot `886c014` |
| `docs/demo.md` | Created | 8-10 minute presenter runbook, staged CLI relay, cleanup, automated fallback and smoke commands |
| `docs/build_course_report.py` | Tested | Standard-library Markdown/HTML export and optional PDF using installed Chrome; generated output ignored |
| `docs/P2P_COMPLETE_PROJECT_HANDBOOK.md` | Implemented | Self-contained 21-chapter study guide, 100 answered viva questions, diagrams, glossary, code-grounded algorithms and recorded evidence |
| `docs/P2P_VIVA_QUICK_REVISION.md` | Implemented | Independent concise revision guide with formulas, protocol, metrics and limitations |
| `docs/P2P_DEMO_SCRIPT.md` | Implemented | Three-console setup, transfer/relay/rate/baseline demonstrations, narration, troubleshooting and explicit rehearsal scope |
| `docs/P2P_SOURCE_CODE_MAP.md` | Implemented | 31 Python files/270 definitions, frontend handlers, argument/return/failure boundaries and execution chains |
| `docs/P2P_HANDBOOK_COVERAGE_CHECKLIST.md` | Implemented | Investigation checklist, exact new verification outcomes, unresolved gaps and Notion publication evidence |

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

### Download-only baseline verification (2026-11-19)

Validation performed on `feat/download-only-baseline`, based on `a7a19a9`.
Commands used the existing virtual environment; no dependencies were installed.

| Command | Actual result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest` (before edits) | 304 passed, 1 upstream warning in 11.92s |
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_cli.py tests/unit/test_scheduler.py tests/integration/test_download_only.py tests/e2e/test_full_transfer.py` (first run) | 2 failed, 30 passed in 9.67s; new unit fixture fed a socket mock instead of the worker inbox; corrected fixture |
| Same focused command after fixture correction | 32 passed in 3.59s |
| `.\.venv\Scripts\python.exe -m pytest` (final code) | 310 passed, 1 upstream Starlette/httpx warning in 10.18s |
| `.\.venv\Scripts\python.exe -m pytest tests/integration/test_download_only.py tests/e2e/test_full_transfer.py` (5 consecutive runs) | 5 passed per run (25 test executions); 3.37s, 3.18s, 3.31s, 3.12s, 2.86s |
| `.\.venv\Scripts\python.exe -m ruff format src/p2p/cli.py src/p2p/peer/client.py src/p2p/peer/downloader.py tests/e2e/test_full_transfer.py tests/unit/test_cli.py tests/unit/test_scheduler.py tests/integration/test_download_only.py` | 3 files reformatted, 4 left unchanged |
| `.\.venv\Scripts\python.exe -m ruff check .` | All checks passed! |
| `.\.venv\Scripts\python.exe -m ruff format --check src/p2p tests` | 39 files already formatted |
| `.\.venv\Scripts\python.exe -m mypy src/p2p tests` (twice) | Success: no issues found in 39 source files |
| `.\.venv\Scripts\python.exe -m p2p.cli download-file --help` | Exited 0; listed `--no-upload` and its baseline description |
| `git diff --check` | Exited 0; no whitespace errors (Git emitted an LF/CRLF conversion notice for `docs/protocol.md`) |

These are correctness checks. No benchmark workload, timing dataset, or
performance comparison was run.

### Token-bucket rate limiter and metrics verification (2026-11-20)

Validation performed on `feat/download-only-baseline`.
Commands used the existing virtual environment; no external dependencies were installed.

| Command | Actual result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_rate_limiter.py` | 28 passed in 1.68s |
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_cli.py tests/unit/test_swarm_peer.py tests/unit/test_scheduler.py` | 44 passed in 8.35s |
| `.\.venv\Scripts\python.exe -m pytest` | 343 passed, 1 upstream Starlette/httpx warning in 13.01s |
| `.\.venv\Scripts\python.exe -m ruff check .` | All checks passed! |
| `.\.venv\Scripts\python.exe -m ruff format --check src/p2p tests` | 41 files already formatted |
| `.\.venv\Scripts\python.exe -m mypy src/p2p tests` | Success: no issues found in 41 source files |
| `git diff --check` | Exited 0; no whitespace errors |

### Experiment runner and plot verification (2026-11-20)

Existing uncommitted Milestone 8 work on `feat/download-only-baseline`, based on
`b926ada`, was preserved. No dependencies were installed. Added the runner,
analysis, failure-metric retention and optional per-client scheduler seed.

| Command | Actual result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_benchmark_peer_metrics.py` (before fix) | 2 failed: transfer/cancellation counters were zero; regression reproduced |
| Same regression command after metric retention fix | 2 passed in 3.84s |
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_benchmarks.py tests/unit/test_benchmark_peer_metrics.py tests/integration/test_benchmark_runner.py` (initial runner) | 29 passed in 24.32s |
| `.\.venv\Scripts\python.exe -m pytest -ra` (before scheduler seed option) | 373 passed, 1 warning in 34.78s |
| `.\.venv\Scripts\python.exe -m pytest -ra` (final implementation) | 376 passed, 1 warning in 29.03s |
| `.\.venv\Scripts\python.exe -m pytest tests/integration/test_benchmark_runner.py -q` (5 consecutive runs after seed option) | 7 passed per run; 35 test executions, all exited 0 |
| `.\.venv\Scripts\python.exe -m ruff check .` | All checks passed! |
| `.\.venv\Scripts\python.exe -m ruff format --check src/p2p tests bench` | 47 files already formatted |
| `.\.venv\Scripts\python.exe -m mypy src/p2p tests bench` | Success: no issues found in 47 source files |
| `git diff --check` | Exited 0; LF/CRLF conversion notices only |
| `python bench/run_experiments.py --help`; `python bench/plot_results.py --help` (venv Python) | Both exited 0; direct and module entry points supported |
| Seeded smoke runner command in `docs/experiments.md` | Exited 0, 30 observations; all final hashes passed; baseline leecher uploads zero; P2P leecher uploads observed |
| `python -m bench.plot_results --csv bench/results/smoke-seeded.csv --output-dir bench/plots/smoke-seeded --experiment-id m8-smoke-seeded` (venv Python) | Exited 0; 4 plots plus summary and audit generated |
| `.\.venv\Scripts\python.exe -m bench.run_experiments --experiment-id m8-loopback-20261120` | Exited 0; `Wrote 180 observations to bench/results/experiments.csv`; 48 trials, all succeeded |
| `.\.venv\Scripts\python.exe -m bench.plot_results --experiment-id m8-loopback-20261120` | Exited 0; four PNGs generated plus summary/audit CSV; completion and peer-share charts visually inspected |
| `.\.venv\Scripts\python.exe -` (inline standard-library CSV audit) | Passed: 48 complete trials, 180 verified rows, 150 measured/30 warmup; 5 measured + 1 warmup per configuration; upload totals balance; retries and integrity failures zero; plot audit 40 included/8 warmup |

Initial lint/type checks found formatting and type errors that were corrected.
The first direct plot-script help call failed to resolve the `bench` package;
the import now supports both invocation forms. An early smoke with the old
fixed-zero scheduler seed had no peer uploads; the final harness records
distinct client seeds paired between modes. Smoke data is kept separate from
the default performance dataset and supplies no performance conclusion.

The full default sweep is **Run**, collected from `b926ada` plus the then-dirty
working tree (`git_dirty=true`). The implementation and raw CSV are versioned
together in the Milestone 8 commit on `feat/download-only-baseline`; the raw
metadata remains unchanged to describe the actual collection state. Measured
results and limitations are recorded in `docs/experiments.md`. Generated
PNGs/derived CSVs remain ignored and are reproducible with the plotting command
above.

### Course report and demo preparation (2026-11-20)

Prepared the editable report and demo runbook using the committed experiment
`m8-loopback-20261120` and implementation snapshot `886c014`. Exported a
self-contained HTML and seven-page PDF containing all four measured plots.
Every PDF page was rendered with the installed Windows PDF renderer and
visually inspected; the first export's methodology overflow was corrected.
No software or dependencies were installed. Generated exports are ignored
under `output/`; rebuild with `python docs/build_course_report.py --pdf` after
plot regeneration. Chrome/Chromium must already be installed for PDF export;
HTML export uses only the standard library.

| Command | Actual result |
|---|---|
| `.\.venv\Scripts\python.exe -m bench.plot_results --experiment-id m8-loopback-20261120` | Exited 0; four measured plots regenerated without recollecting or changing raw data |
| Demo's selected E2E/corruption/disconnect pytest command in `docs/demo.md` | 5 passed in 1.93s |
| Demo input generator and `python -m p2p.cli create-manifest ...` commands in `docs/demo.md` (venv Python) | Created 1 MiB source and manifest under ignored `downloads/course-demo/` |
| Tiny runner/plot commands in `docs/demo.md` | Both exited 0; six verified client observations, four smoke plots plus summary/audit |
| `.\.venv\Scripts\python.exe docs/build_course_report.py --pdf` | Exited 0; `Exported output/pdf/course-report.pdf`; final PDF has seven pages and correct 1/7..7/7 numbering |
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_course_report_export.py` | 2 passed in 0.76s; HTML escaping/embedding, page breaks and missing-browser handling |
| `.\.venv\Scripts\python.exe -m pytest -ra` | 378 passed, 1 upstream warning in 26.17s |
| `.\.venv\Scripts\python.exe -m ruff check docs/build_course_report.py tests/unit/test_course_report_export.py` | All checks passed! |
| `.\.venv\Scripts\python.exe -m mypy docs/build_course_report.py tests/unit/test_course_report_export.py` | Success: no issues found in 2 source files |
| `.\.venv\Scripts\python.exe -m ruff check .` (while concurrent feature work was appearing) | Not clean: issues in unrelated peer/web edits; those files left untouched |
| `.\.venv\Scripts\python.exe -m ruff format --check src/p2p tests bench docs/build_course_report.py` | Not clean: 5 files in concurrent feature work would be reformatted; 51 already formatted |
| `.\.venv\Scripts\python.exe -m mypy src/p2p tests bench docs/build_course_report.py` | Not clean: 2 export-attribute errors in `tests/unit/test_benchmarks.py` following concurrent benchmark refactoring |

The four-terminal CLI runbook is prepared but was not newly rehearsed in full
interactive terminals during this task. Its component CLI/relay behaviors are
covered by tests and the historical Windows smoke. Do not interpret the tiny
demo's timing or test runtime as benchmark evidence. The report explicitly
describes the committed measurement snapshot, not concurrent feature edits.

Documentation gaps corrected: the CLI guide still called rate limiting and
the runner planned; README omitted Milestone 8 from its completed list; the
architecture guide named a nonexistent `safe_target()` helper. Other specs
were left unchanged.

### Local console verification (2026-11-20)

Work on `feat/local-web-console`; existing dependencies only. No new software was
installed and no new performance sweep was run. Verification completed before
the implementation commit. Existing report/demo documents were preserved. The
original CLI and TCP wire protocol are unchanged.

| Command | Actual result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest tests/integration/test_web_console.py -x -o addopts='' -q` (initial) | 1 failed, 1 passed; source contributions included a zero-byte baseline connection; excluded zero-byte entries from the copied source map |
| Same API file after correction | 8 passed; after final-hash failure coverage, 9 passed |
| `.\.venv\Scripts\python.exe -m pytest tests/integration/test_web_console.py tests/e2e/test_web_http_transfer.py tests/integration/test_tracker_api.py -o addopts='' -q` | 26 passed in 41.76s |
| `.\.venv\Scripts\python.exe -m pytest -ra` (before final cancellation regression) | 389 passed, 1 upstream Starlette/httpx warning in 82.51s |
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_web_service.py -o addopts='' -q` | First 1 failed: worker validation error replaced cancellation; after joining with `gather(return_exceptions=True)`, 1 passed in 1.25s |
| `.\.venv\Scripts\python.exe -m pytest tests/integration/test_web_console.py tests/unit/test_web_service.py -o addopts='' -q` (5 consecutive runs) | 10 passed each; 50 executions; 4.70s, 3.56s, 4.80s, 3.85s, 3.30s |
| `.\.venv\Scripts\python.exe -m p2p.web --help` | Exited 0; listed port, tracker URL and workspace options |
| `.\.venv\Scripts\python.exe bench/plot_results.py --help` | Exited 0; existing direct plotting entry point preserved |
| `.\.venv\Scripts\python.exe -m pytest -ra` (final code) | **390 passed, 1 warning in 61.51s**; existing upstream Starlette/httpx warning |
| `.\.venv\Scripts\python.exe -m ruff check .` (final code) | **All checks passed!** |
| `.\.venv\Scripts\python.exe -m ruff format --check src/p2p tests bench` | **58 files already formatted** |
| `.\.venv\Scripts\python.exe -m mypy src/p2p tests bench` | **Success: no issues found in 58 source files** |
| `node --check src/p2p/web/static/app.js` | Exited 0; no output |
| `git diff --check` | Exited 0; no whitespace errors; LF/CRLF conversion notice for `docs/experiments.md` |

The process E2E starts a real Uvicorn tracker and two independent console
processes on ephemeral loopback HTTP ports. It imports a 1 MiB file, seeds with
a 512 KiB/s cap, verifies downloaded SHA-256 and bytes, stops the origin and
checks an actual completed-peer TCP relay, then verifies two baseline clients
receive only origin payloads and upload none. It reads the real benchmark CSV,
requires graceful server exit without forced termination and checks that console
shutdown removes all remaining tracker memberships. API tests additionally cover
partial verified progress, three baseline clients, final-file corruption, unsafe
paths/manifests, request guards, limits, missing data, no peers and cancellation.

Initial lint/type issues (formatting and benchmark function re-exports) were
corrected. Browser screenshot/interaction tests were not run: both browser and
native Computer Use entry points reported a missing native pipe. JavaScript
syntax checks and HTTP static-asset delivery are covered, not visual layout.

### Frontend redesign verification (2026-11-20)

The user approved the audit/specification/implementation plan before code edits.
Checkpoints preserve both original source and the approved planning state.
Frontend HTML/CSS/JS, local assets and asset packaging changed; no Python source,
existing test or benchmark data changed. Exact commands, early automation
failures and corrections, inspected screenshots, file inventory and remaining
limits are in [frontend-redesign-verification.md](frontend-redesign-verification.md).

- Latest full suite: `.\.venv\Scripts\python.exe -m pytest -ra` reported
  `390 passed, 1 warning in 71.35s (0:01:11)`.
- Ruff: `All checks passed!`; formatting: `58 files already formatted`;
  mypy: `Success: no issues found in 58 source files`; JS syntax checks exited 0.
- `node tests/browser/console.mjs`: 13 workflow groups passed, including
  source/manifest import, SHA-256-checked export, capped transfer, relay,
  baseline, cancellation, five viewport widths, offline state and recovery.
  The final repeat after visual polish also passed 13 groups and required empty
  tracker membership after graceful console shutdown.
- A locally built wheel includes the fonts, licenses, provenance and favicon.
  No dependencies were installed and no new experiment measurement was run.

## 6. Open Issues & Known Limitations

- The redesign's Chrome workflows and responsive screenshots passed. Screen
  readers, native zoom-menu operation, other browser engines and other operating
  systems remain unverified. Existing API tests cover final-file corruption;
  that fault was not newly injected through a browser workflow.
- Console files persist in the configured workspace. Catalogs/history are
  in-memory and do not restore after restart; downloads do not resume. UI source
  and download sizes are capped at 128 MiB; caps/settings apply at peer creation.
- Console experiment display needs a source checkout containing the raw CSV and
  `bench/`; it does not execute experiments or invent unavailable measurements.

- Milestone 3 storage operations are synchronous; async callers must offload large file work and serialize access to a shared `StorageManager`.
- Full test runs emit one upstream Starlette/httpx deprecation warning; it does not fail tests.
- Automated E2E tests use an in-process tracker. The single interactive Windows smoke run verified Ctrl+C shutdown and stopped-event deregistration for one tracker, seeder, and leecher; repeated signal stress and other operating systems were not exercised.
- A repository-wide `ruff format --check` flags 17 Markdown files with fenced examples in `.agents/skills/` and `docs/manifest-format.md`; the documented source-and-test command (`ruff format --check src/p2p tests`) passes.
- Each peer worker currently has one outstanding request at a time; per-peer pipelining is not implemented.
- Download-only clients retain their listeners and consume connection slots;
  `is_seeder` still reports local completeness, not upload capability. An
  origin-only baseline requires every client to disable uploads and exactly one
  uploading seed. The flag has automated loopback/CLI coverage but has not had
  a separate multi-process Windows smoke test.
- Benchmark results use one Python process, loopback TCP and an in-process
  ASGI tracker; they do not establish deployment or real-network performance.
  Resource usage/RAM and external activity are not automatically measured.
  Generated plots/summary CSVs are ignored and regenerated from raw observations.

## 7. Decisions Needed

- No pending design decision for the loopback runner. A separate-process or
  multi-machine performance harness would require an explicit follow-up scope.

## 8. Next Steps

- Review the Milestone 8 feature branch and merge through a pull request.
- Course report and demo runbook are prepared: `docs/course-report.md` and
  `docs/demo.md`; exports are in `output/`. Rehearse the manual four-terminal
  relay sequence before the live presentation; the automated fallback is tested.
- Optional follow-up: separate-process or multi-machine benchmarks and repeated
  shutdown testing on other operating systems. These are not required to
  complete the current eight-milestone implementation plan.
