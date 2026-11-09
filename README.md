# BitTorrent-Style P2P File Distribution System

A Python 3.12+ project for a BitTorrent-style Peer-to-Peer (P2P) file distribution system.

The project is being developed in milestones. Milestones 1 through 6 are tested.
Milestone 6 provides bounded downloads from already-connected peers, storage
verification, retries/failover, HAVE updates, and cancellation cleanup. Tracker
discovery, CLI workflows, and full tracker-plus-swarm end-to-end testing remain
Milestone 7 work. See the [project status](docs/project-status.md) for current
scope and verification.

---

## 1. Project Overview & Architecture

- **Implemented and tested:** Length-prefixed TCP framing and message codecs (`HANDSHAKE`, `BITFIELD`, `REQUEST`, `PIECE`, `HAVE`); FastAPI Tracker HTTP control plane (`/announce`, `/swarms/{id}/peers`, `/health`) with in-memory registry and stale-peer expiry; v1 manifest creation/validation and verified chunk storage; peer TCP connection engine; Milestone 6 scheduler and `SwarmDownloader` for bounded concurrent transfers across already-connected peers, storage verification, retries, peer failover, HAVE broadcast/update, and cancellation cleanup.
- **Planned:** Tracker-driven peer discovery, CLI workflows, and full tracker-plus-multi-leecher end-to-end transfer (Milestone 7); controlled benchmark harness (Milestone 8).

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
│   ├── tracker/      # Tracker HTTP control plane and swarm registry
│   ├── peer/         # Peer networking, download scheduler, worker and coordinator
│   ├── protocol/     # Implemented wire framing codec and message definitions
│   ├── storage/      # Implemented manifest validation and verified file storage
│   └── config.py     # System constants, defaults, and timeouts
├── tests/            # Automated test suite
│   ├── unit/         # Codec, manifest, storage, scheduler, and worker unit tests
│   ├── integration/  # Tracker API and peer loopback tests
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

# Check formatting across implemented source and tests
ruff format --check src/p2p tests

# Run static type checking
mypy src/p2p tests
```

---

## 5. Active Phase & Documentation Status

- **Current active phase:** Milestone 7 — End-to-End Swarm Integration & Seeder CLI.
- **Completed milestones:**
  - Milestone 1 — Project Foundation & Tooling Setup
  - Milestone 2 — Wire Framing Codec & Protocol Messages
  - Milestone 3 — Manifest Engine & Storage Integrity
  - Milestone 4 — Tracker HTTP Control Plane
  - Milestone 5 — Peer TCP Connection Engine
  - Milestone 6 — Download Scheduler & Swarm Orchestration
- **Latest verification (2026-11-09):** `pytest -ra` — 273 passed with one Starlette/httpx deprecation warning; `ruff check .`, `ruff format --check src/p2p tests`, and `mypy src/p2p tests` — passed. The focused downloader suite reports 90% statement coverage. See the [project status](docs/project-status.md) for exact commands and remaining Milestone 7 scope.
- **AI guidance:** [AGENTS.md](AGENTS.md)
- **Architecture overview:** [docs/architecture.md](docs/architecture.md)
- **Protocol specification:** [docs/protocol.md](docs/protocol.md)
- **Manifest specification:** [docs/manifest-format.md](docs/manifest-format.md)
- **Implementation plan:** [docs/implementation-plan.md](docs/implementation-plan.md)
- **Project status:** [docs/project-status.md](docs/project-status.md)
