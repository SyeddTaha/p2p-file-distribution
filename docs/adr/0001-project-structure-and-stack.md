# 0001. Project Structure and Stack Selection

- Status: Accepted
- Date: 2026-10-10

## Context
The project requires a BitTorrent-style Peer-to-Peer file distribution system demonstrating networking fundamentals, asynchronous TCP streams, tracker HTTP control plane, file integrity verification, automated tests, and empirical performance benchmarking.

We need to select an approved technical stack and project layout that supports modularity, type safety, non-blocking I/O, and testability while avoiding unnecessary complexity.

## Decision
We choose the following stack and structure:
- **Language & Runtime:** Python 3.12+ using built-in `asyncio` for non-blocking TCP socket streams.
- **Tracker HTTP Control Plane:** FastAPI with Uvicorn server, keeping tracker state **in-memory**.
- **Integrity Verification:** Built-in `hashlib.sha256` for chunk and file integrity.
- **Manifest Format:** JSON manifest files detailing chunk size, hashes, and canonical Swarm ID.
- **Test Framework:** `pytest` with `pytest-asyncio` for unit, integration, and E2E testing.
- **Code Quality:** Ruff for linting and formatting; `mypy` for static type checking.
- **Project Structure:**
  - `src/p2p/` for application code (`config.py`, `tracker/`, `peer/`, `protocol/`, `storage/`).
  - `tests/` (`unit/`, `integration/`, `e2e/`).
  - `bench/` (`results/`, `plots/`).
  - `docs/` (`adr/`, specs, status).

## Alternatives Considered
- **Flask for Tracker:** FastAPI was chosen over Flask because FastAPI natively supports Python async handlers (`async def`), integrating seamlessly with `asyncio`.
- **Relational / Redis Database for Tracker:** Rejected as per AGENTS.md non-goals. In-memory state is sufficient for course laboratory scale and can be recovered by peer re-announcements.
- **Third-Party Binary Serialization (Protobuf/MsgPack):** Rejected to keep protocol dependencies minimal and allow custom TCP framing engineering.

## Consequences
- Zero external database or complex backend infrastructure dependencies.
- Code logic is decoupled from I/O so unit testing can run without opening network sockets.
- Full type safety across protocol and storage layers.
