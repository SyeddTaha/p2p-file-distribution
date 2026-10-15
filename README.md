# BitTorrent-Style P2P File Distribution System

A Python 3.12+ project for a BitTorrent-style Peer-to-Peer (P2P) file distribution system.

The project is being developed in milestones. The protocol framing codec and message
serialization, plus Milestone 3 manifest and verified storage, are implemented and
tested. Tracker peer management, peer connections, download scheduling, end-to-end
transfers, and benchmarking remain planned unless noted in the
[project status](docs/project-status.md).

---

## 1. Project Overview & Architecture

- **Implemented:** Length-prefixed TCP framing and message codecs for `HANDSHAKE`, `BITFIELD`, `REQUEST`, `PIECE`, and `HAVE`; a minimal tracker health endpoint; v1 manifest creation, validation, atomic JSON output, canonical Swarm IDs, safe destination paths, verified chunk storage, and atomic file finalization.
- **Planned:** Tracker swarm/peer registry, peer TCP connection lifecycle, download scheduling, complete swarm transfers, and controlled benchmarks.

---

## 2. Directory Structure

```
├── .agents/skills/   # Shareable project & ecosystem AI skills (12 skills)
├── bench/            # Reserved for planned benchmark scripts, data, and plots
├── context/          # Original project requirements specification
├── docs/             # Technical specifications, ADRs, status, testing guides
│   ├── adr/          # Architecture Decision Records
│   ├── architecture.md
│   ├── protocol.md
│   ├── manifest-format.md  # Implemented v1 format specification
│   ├── implementation-plan.md
│   ├── testing.md
│   ├── experiments.md
│   └── project-status.md
├── src/p2p/          # Current application package
│   ├── tracker/      # Minimal health endpoint; swarm tracking is planned
│   ├── peer/         # Planned peer networking and scheduler components
│   ├── protocol/     # Implemented wire framing codec and message definitions
│   ├── storage/      # Implemented manifest validation and verified file storage
│   └── config.py     # System constants, defaults, and timeouts
├── tests/            # Automated test suite
│   ├── unit/         # Codec, manifest, storage, and path safety unit tests
│   ├── integration/  # No integration tests currently checked in
│   └── e2e/          # Planned full multi-peer transfer tests
├── pyproject.toml    # Dependencies and tool configurations (pytest, ruff, mypy)
├── requirements.txt  # Quick teammate dependency requirements file
└── README.md         # Quick start & repository guide
```

---

## 3. Quick Start for Teammates & Developers

### Requirements
- Python 3.12 or higher

### Environment Setup (Single Command Step)

```bash
# 1. Create a virtual environment
python -m venv .venv

# 2. Activate the virtual environment
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

# 3. Install project dependencies via requirements.txt
pip install -r requirements.txt
```

---

## 4. Development & Testing Commands

```bash
# Run full automated test suite
pytest

# Run linting checks
ruff check .

# Check formatting for implemented protocol and storage code/tests
ruff format --check src/p2p/protocol src/p2p/storage tests/unit/test_protocol.py tests/unit/test_storage.py

# Run static type checking
mypy src/p2p tests
```

---

## 5. Active Phase & Documentation Status

- **Current active phase:** Milestone 4 — Tracker HTTP Control Plane is **Planned / Next Up**.
- **Completed milestones:** Milestone 1 — Project Foundation & Tooling Setup;
 Milestone 2 — Wire Framing Codec & Protocol Messages;
Milestone 3 — Manifest Engine & Storage Integrity.
 See the [implementation plan](docs/implementation-plan.md).
- **Latest verification (2026-10-15):** `pytest` — 105 passed with one Starlette/httpx deprecation warning; `ruff check .` — passed; `mypy src/p2p` — passed (11 source files). Targeted protocol/storage format check passed. See the [project status](docs/project-status.md) for the recorded commands.
- **Formatting note:** The protocol-scoped `ruff format --check src/p2p/protocol tests/unit/test_protocol.py` passed previously. A broader `ruff format --check src tests` reported formatting needed in `src/p2p/config.py`.
- **AI guidance:** [AGENTS.md](AGENTS.md)
- **Architecture overview:** [docs/architecture.md](docs/architecture.md)
- **Protocol specification:** [docs/protocol.md](docs/protocol.md)
- **Manifest specification:** [docs/manifest-format.md](docs/manifest-format.md)
- **Implementation plan:** [docs/implementation-plan.md](docs/implementation-plan.md)
- **Project status:** [docs/project-status.md](docs/project-status.md)
