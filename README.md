# BitTorrent-Style P2P File Distribution System

A Python 3.12+ project for a BitTorrent-style Peer-to-Peer (P2P) file distribution system.

Milestones 1 through 7 are implemented and tested. Milestone 7 adds tracker-aware
peer lifecycle management, verified chunk seeding, four CLI commands, and a
loopback end-to-end transfer with three concurrent leechers plus a staged
verified leecher-to-leecher transfer. Its final Windows multi-process smoke
test also verified a 1 MiB download, byte/hash equality, Ctrl+C shutdown, and
tracker peer removal. See [project status](docs/project-status.md) and the
[testing guide](docs/testing.md) for results and the reproducible procedure.
Milestone 8 includes tested download-only baseline controls, upload rate limits,
transfer metrics, a reproducible N=1,2,4,8 experiment runner and headless plots.
See [experiments](docs/experiments.md) for commands, recorded results and limits.
The default sweep has run: 48 trials and 180 verified client observations in
[`bench/results/experiments.csv`](bench/results/experiments.csv). Measurements
are limited to one host with loopback TCP and an in-process tracker.

---

## 1. Project Overview & Architecture

- **Implemented and tested:** Length-prefixed TCP framing and message codecs (`HANDSHAKE`, `BITFIELD`, `REQUEST`, `PIECE`, `HAVE`); FastAPI Tracker HTTP control plane with in-memory registry and stale-peer expiry; v1 manifest creation/validation and verified chunk storage; bounded peer server and peer connections; scheduler and `SwarmDownloader`; `SwarmPeer` tracker announcements, discovery, seeding, multi-peer downloads, and lifecycle cleanup; CLI and a tracker + seeder + three-leecher loopback E2E test; download-only baseline mode (`--no-upload`); token-bucket upload rate limiter (`TokenBucketRateLimiter`, `--upload-rate-limit`).
- **Benchmarking:** Automated Client-Server/P2P parameter sweeps, append-only raw CSV, whole-trial failure auditing, and plots with mean/sample-SD error bars (Milestone 8).

---

## 2. Directory Structure

```
├── .agents/skills/   # Shareable project & ecosystem AI skills (12 skills)
├── bench/            # Experiment runner, plotting script, raw results and generated plots
├── context/          # Original project requirements specification
├── docs/             # Technical specifications, ADRs, status, testing guides
│   ├── adr/          # Architecture Decision Records
│   ├── architecture.md
│   ├── cli.md
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
│   └── e2e/          # Tracker + seeder + concurrent leecher transfer tests
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

## 5. CLI Quick Start

Install the package in editable mode. Run `create-manifest` once, then start
the tracker, seeder, and each leecher in separate terminals:

```powershell
p2p tracker-start --host 127.0.0.1 --port 8000
p2p create-manifest .\payload.bin --output .\payload.manifest.json
p2p seed-file .\payload.manifest.json .\payload.bin --tracker-url http://127.0.0.1:8000
p2p download-file .\payload.manifest.json --download-dir .\downloads --tracker-url http://127.0.0.1:8000
```

`seed-file` and `download-file` remain running to serve the swarm and stop on
Ctrl+C. Use `download-file --no-upload` on every client for the origin-only
baseline; those clients stay online without serving chunks. Both commands accept
`--upload-rate-limit <bytes/sec>` to cap outbound bandwidth via token bucket.
Distribute the manifest file to downloaders out of band. See the
[CLI guide](docs/cli.md) for command behavior and options.

## 6. Active Phase & Documentation Status

- **Current state:** Milestones 1–7 are tested. Milestone 8 includes baseline controls, token-bucket upload limits, transfer counters, experiment sweeps and analysis. See [project status](docs/project-status.md) for verification and [experiments](docs/experiments.md) for measurement scope.
- **Completed milestones:**
  - Milestone 1 — Project Foundation & Tooling Setup
  - Milestone 2 — Wire Framing Codec & Protocol Messages
  - Milestone 3 — Manifest Engine & Storage Integrity
  - Milestone 4 — Tracker HTTP Control Plane
  - Milestone 5 — Peer TCP Connection Engine
  - Milestone 6 — Download Scheduler & Swarm Orchestration
  - Milestone 7 — End-to-End Swarm Integration & Seeder CLI
- **Latest verification:** See [project status](docs/project-status.md) for the latest full suite, focused E2E checks, CLI verification, and lint/type/format results.
- **AI guidance:** [AGENTS.md](AGENTS.md)
- **Architecture overview:** [docs/architecture.md](docs/architecture.md)
- **Protocol specification:** [docs/protocol.md](docs/protocol.md)
- **Manifest specification:** [docs/manifest-format.md](docs/manifest-format.md)
- **Implementation plan:** [docs/implementation-plan.md](docs/implementation-plan.md)
- **CLI guide:** [docs/cli.md](docs/cli.md)
- **Project status:** [docs/project-status.md](docs/project-status.md)
