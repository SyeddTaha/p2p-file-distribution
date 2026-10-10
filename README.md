# BitTorrent-Style P2P File Distribution System

A lightweight, reliable Peer-to-Peer (P2P) file distribution framework built in Python 3.12+ for a university Computer Networks course.

The system demonstrates custom application-layer TCP framing, parallel piece downloads, centralized HTTP tracking, cryptographic integrity verification (SHA-256), path safety, fault tolerance, and empirical performance benchmarking comparing P2P against a Client-Server baseline.

---

## 1. Project Overview & Architecture

- **Tracker Service (HTTP Control Plane):** Built with FastAPI. Maintains in-memory swarm registries, processes peer announcements (`started`, `heartbeat`, `completed`, `stopped`), and evicts stale peers using an injectable clock interface.
- **Peers (TCP Data Plane):** Concurrent TCP servers and clients exchanging piece data over a custom length-prefixed wire protocol (`HANDSHAKE`, `BITFIELD`, `REQUEST`, `PIECE`, `HAVE`).
- **Storage & Integrity Layer:** Divides files into fixed chunks (default 256 KiB), creates JSON manifests, computes canonical Swarm IDs, writes chunks safely to `.part` files, and atomically reassembles verified output files.
- **Benchmark Suite:** Empirical test harness comparing total distribution makespan and throughput across Client-Server vs P2P modes under controlled rate limits.

---

## 2. Directory Structure

```
├── .agents/skills/   # Shareable project & ecosystem AI skills (12 skills)
├── bench/            # Benchmark scripts, raw CSV data, and generated plots
├── context/          # Original project requirements specification
├── docs/             # Technical specifications, ADRs, status, testing guides
│   ├── adr/          # Architecture Decision Records
│   ├── architecture.md
│   ├── protocol.md
│   ├── manifest-format.md
│   ├── implementation-plan.md
│   ├── testing.md
│   ├── experiments.md
│   └── project-status.md
├── src/p2p/          # Core Python application package
│   ├── tracker/      # FastAPI tracker control plane
│   ├── peer/         # TCP server, client, scheduler, connection manager
│   ├── protocol/     # Binary wire framing codec & message definitions
│   ├── storage/      # JSON manifest parser, path sanitizer, chunk integrity
│   └── config.py     # System constants, defaults, and timeouts
├── tests/            # Automated test suite
│   ├── unit/         # Codec, manifest, scheduler, path safety unit tests
│   ├── integration/  # TCP handshake, loopback peer, tracker HTTP tests
│   └── e2e/          # Full multi-peer swarm transfer tests
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

# Run code formatting check
ruff format --check .

# Run static type checking
mypy src/p2p
```

---

## 5. Active Phase & Documentation Status

- **Current Active Milestone:** **Milestone 2 (Wire Framing Codec & Messages)**
- **Completed Milestones:** **Milestone 1 (Foundation & Tooling Setup)** - `pytest` (4/4 passed), `ruff` clean, `mypy` clean.
- **Shared AI Skills (12 Skills):** Documented in [`AGENTS.md`](file:///c:/Users/tahaj/OneDrive%20-%20FAST%20National%20University/5th%20Sem%20CN/p2p-file-distribution/AGENTS.md) under Section 9.
- **Architecture Overview:** [`docs/architecture.md`](file:///c:/Users/tahaj/OneDrive%20-%20FAST%20National%20University/5th%20Sem%20CN/p2p-file-distribution/docs/architecture.md)
- **Protocol Specification:** [`docs/protocol.md`](file:///c:/Users/tahaj/OneDrive%20-%20FAST%20National%20University/5th%20Sem%20CN/p2p-file-distribution/docs/protocol.md)
- **Manifest Specification:** [`docs/manifest-format.md`](file:///c:/Users/tahaj/OneDrive%20-%20FAST%20National%20University/5th%20Sem%20CN/p2p-file-distribution/docs/manifest-format.md)
- **Implementation Plan:** [`docs/implementation-plan.md`](file:///c:/Users/tahaj/OneDrive%20-%20FAST%20National%20University/5th%20Sem%20CN/p2p-file-distribution/docs/implementation-plan.md)
- **Project Status:** [`docs/project-status.md`](file:///c:/Users/tahaj/OneDrive%20-%20FAST%20National%20University/5th%20Sem%20CN/p2p-file-distribution/docs/project-status.md)
