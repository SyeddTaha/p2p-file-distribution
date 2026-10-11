# Project Status & Team Workflow Tracking

> Last updated: 2026-10-10. Commit: Initial setup (Milestone 1 Complete).

---

## 1. Project Phase & Milestone Summary

| Milestone | Description | Status | Active / Target Date | Verified Checks |
| :--- | :--- | :---: | :---: | :--- |
| **Milestone 1** | **Project Foundation & Tooling Setup** | **DONE** | 2026-10-10 | `pytest` (4/4 passed), `ruff` (clean), `mypy` (clean) |
| **Milestone 2** | **Wire Framing Codec & Messages** | **DONE** | 2026-10-11 | `pytest` (53/53 passed), `ruff` (clean), `mypy` (clean), 99% coverage |
| **Milestone 3** | **Manifest Engine & Storage Integrity** | PLANNED | Next Up | JSON manifest, SHA-256 chunk/file verifier, `.part` files |
| **Milestone 4** | **Tracker HTTP Control Plane** | PLANNED | To Do | Swarm registry, peer announce/scrape, stale peer expiry |
| **Milestone 5** | **Peer TCP Connection Engine** | PLANNED | To Do | TCP server/client, handshake state machine, bitfields |
| **Milestone 6** | **Download Scheduler & Orchestrator** | PLANNED | To Do | Chunk reservation (`IN_FLIGHT`), retries, HAVE broadcasts |
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
| Manifest | Manifest creation & JSON schema | Planned | No | Milestone 3 |
| Manifest | Manifest validation & Swarm ID | Planned | No | Milestone 3 |
| Storage | Chunk verification (length + SHA-256) | Planned | No | Milestone 3 |
| Storage | Safe paths and `.part` temp files | Planned | No | Milestone 3 |
| Storage | Final file verification and atomic finalize | Planned | No | Milestone 3 |
| Tracker | Basic Health Endpoint | **Tested** | Yes | Verified via `tests/unit/test_health.py` |
| Tracker | Peer registration / announce | Planned | No | Milestone 4 |
| Tracker | Heartbeat and stale-peer expiry | Planned | No | Milestone 4 |
| Peer | Seeding (serving verified chunks) | Planned | No | Milestone 5/7 |
| Peer | Downloading with scheduling | Planned | No | Milestone 6 |
| Peer | Retries, peer failure handling, cancellation | Planned | No | Milestone 6 |
| Testing | Unit tests foundation | **Tested** | Yes | 53 unit tests passing cleanly in 0.95s |
| Benchmarking | Baseline mode & runner | Planned | No | Milestone 8 |

---

## 4. Documentation Status

| Document | State | Purpose |
|---|---|---|
| `README.md` | Created | Quick start, stack, project overview |
| `AGENTS.md` | Updated | Shared AI rules & all 12 project/ecosystem skills |
| `requirements.txt` | Created | Team dependency requirements file |
| `docs/architecture.md` | Created | Components, state ownership, sequence diagrams |
| `docs/protocol.md` | Created | Wire format specification, message codes, state machine |
| `docs/manifest-format.md` | Created | JSON schema, Swarm ID, safe paths |
| `docs/manifest.md` | Created | Linked summary |
| `docs/implementation-plan.md` | Created | Detailed milestones 1 through 8 |
| `docs/testing.md` | Created | Pyramid, scenario matrix, test runner guide |
| `docs/experiments.md` | Created | Hypotheses, control variables, CSV format |
| `docs/adr/0001-project-structure-and-stack.md` | Created | Stack & directory layout |
| `docs/adr/0002-wire-protocol-framing-and-limits.md` | Created | Framing format & security bounds |
| `docs/project-status.md` | Updated | Active phase & milestone tracker |

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
