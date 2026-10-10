# AGENTS.md

Shared, tool-neutral instructions for any AI coding assistant working in this repository.
Humans: see `README.md` and `docs/`. This file is deliberately short; detailed guidance lives in skills under `.agents/skills/`.

## 1. Project objectives and non-goals

**Objective:** a BitTorrent-style Peer-to-Peer file distribution system for a university Computer Networks course, engineered like a real product: correct framing, reliable transfers, verified integrity, tested failure handling, and honest measurements.

Components: a tracker (HTTP control plane), peers (TCP data plane), JSON file manifests, a test suite, and a benchmark harness comparing client-server and P2P distribution.

**Priorities:** networking correctness, backend engineering, distributed-systems reasoning, reliability, clear design.

**Non-goals (do not add without a documented need and an ADR in `docs/adr/`):**
- AI/ML features of any kind inside the product (AI is a development aid only).
- Databases, Redis, message brokers, Docker, cloud services, or a frontend.
- NAT traversal, DHT, encryption/TLS, incentive/choking algorithms, or multi-file torrents.
- Production-grade authentication. The tracker and peers assume a trusted lab network, but still treat all input as untrusted.

## 2. Approved stack and dependency policy

- Python 3.12+, `asyncio` + TCP streams for peer communication.
- FastAPI (with its ASGI server) for tracker HTTP endpoints; tracker state is **in-memory** initially.
- JSON manifests; SHA-256 (`hashlib`) for chunk and whole-file integrity.
- `pytest`, `pytest-asyncio`; Ruff; mypy where practical.
- CSV + Matplotlib for benchmark data and plots; Wireshark for manual inspection.
- Mininet only if practical and available; never required for the test suite.

Dependency policy: prefer the standard library. A new third-party dependency needs a one-paragraph justification in the PR and an entry in `pyproject.toml`. Do not install software, change global configuration, or run network-fetching scripts on a teammate's behalf without being asked.

## 3. Code organization and style

Suggested layout (adjust via ADR, keep `docs/architecture.md` in sync):

```
src/p2p/        # protocol/, peer/, tracker/, storage/, manifest/ subpackages
tests/          # unit/, integration/, e2e/
bench/          # experiment scripts, raw CSV in bench/results/, plots
docs/           # specs, guides, ADRs, status
.agents/skills/ # shared AI skills
```

- Full type hints; `ruff format` and `ruff check` clean; mypy clean on new code where practical.
- Small modules with one responsibility. Pure logic (framing codec, scheduler, manifest validation) must be separable from I/O so it can be unit tested.
- No global mutable state except explicitly owned singletons (e.g. tracker registry). Use dataclasses or `NamedTuple` for messages.
- Use `logging`, not `print`, in library code. Never log chunk payloads.
- Constants (limits, timeouts, protocol version) live in one config module, not scattered literals.

## 4. Async and TCP correctness (always apply)

- TCP is a byte stream. Never assume one `recv`/`read` equals one message. Use explicit framing and `readexactly`.
- After `writer.write(...)`, `await writer.drain()`. On teardown: `writer.close()` then `await writer.wait_closed()`.
- Every network `await` that can block on a remote peer has a timeout.
- Never swallow `asyncio.CancelledError`; re-raise after cleanup. Use `asyncio.TaskGroup` or tracked tasks; no orphan tasks.
- Never block the event loop (large hashing or disk I/O uses `asyncio.to_thread` or bounded chunk sizes).
- Bound everything: connections, in-flight requests, frame sizes, queue lengths.

## 5. Security and input validation

- All remote data (wire messages, tracker responses, manifests) is untrusted. Validate type, length, range, and hash before use.
- Enforce maximum frame and field sizes *before* allocating buffers.
- Sanitize file names from manifests; never write outside the configured download directory.
- No secrets, credentials, tokens, or machine-specific paths in the repository.
- Do not use `eval`, `pickle`, or unsafe deserialization of network data.

## 6. Testing expectations

- Every behavior change ships with tests in the same change. Bug fixes start with a failing regression test.
- Tests are deterministic, use loopback (`127.0.0.1`) with ephemeral ports, use `tmp_path`, and never touch the Internet.
- Run `pytest`, `ruff check`, and `mypy` (where configured) before declaring work done.
- **Report results honestly:** state exactly which commands you ran and what they printed. If something was not run, say so. Never claim a test passed, or a benchmark ran, when it did not.

## 7. Documentation requirements

Update docs in the same change as the code: `docs/protocol.md`, `docs/manifest.md`, `docs/architecture.md`, `docs/testing.md`, `docs/experiments.md`, `docs/adr/`, and `docs/project-status.md`. Status entries use the states *Planned / Partially implemented / Implemented / Tested*. Do not describe planned features as working.

## 8. Git workflow

- Never rewrite shared history (no force-push, no rebase of pushed branches) and never commit directly to `main`.
- Feature branches, small reviewable commits (one logical change each), imperative commit messages.
- Do not commit generated data, caches, virtualenvs, `.pcap` files, or personal settings. Raw benchmark CSVs *are* committed under `bench/results/` when they back a claim in the docs.
- Do not run destructive commands (`rm -rf`, `git reset --hard`, `git clean`) without explicit instruction.

## 9. Using skills

Skills live in `.agents/skills/<name>/SKILL.md`. Read the relevant skill *before* starting work in its area. Each skill owns one responsibility:

| Skill | Owns / Scope |
|---|---|
| `tcp-protocol-engineering` | Wire format: framing, message types (`HANDSHAKE`, `BITFIELD`, `REQUEST`, `PIECE`, `HAVE`), parsing, timeouts, versioning |
| `p2p-distributed-systems` | Tracker semantics, swarm state, scheduling, concurrency, peer failure, worker lifecycle |
| `chunk-storage-integrity` | JSON manifest, SHA-256 chunk/file hashing, disk layout, safe paths (`.part`), reconstruction, corruption |
| `network-testing-reliability` | Test strategy, fixtures, fault injection, loopback socket testing, honest reporting |
| `network-benchmarking` | Experiments, metrics, CSV/plots, client-server baseline comparison |
| `engineering-documentation` | Docs structure, ADRs, project status tracking, writing standards |
| `async-python-patterns` | Python `asyncio` patterns, non-blocking socket streams, task groups, async resource management |
| `python-resilience` | Network fault tolerance, socket timeouts, retries, exponential backoff, graceful teardown |
| `fastapi-python` | Tracker HTTP REST endpoints (`/announce`, `/swarms/...`, `/health`), ASGI server patterns |
| `python-testing-patterns` | Pytest fixtures, mock stream helpers, unit/integration test strategies for concurrent systems |
| `python-performance-optimization` | Benchmarking, profiling, memory & network throughput measurement |
| `python-design-patterns` | Clean architecture, single responsibility, decoupling low-level socket I/O from storage & scheduling |

If a task spans skills, follow each for its own part and do not restate another skill's rules. If skills conflict, the more specific skill wins for its owned area; if still unclear, ask the team and record the decision in an ADR. Treat skill files as code: they are reviewed in PRs (see `docs/ai-tooling.md`).

## 10. Long-term project context

Chat history is not memory. Anything a future contributor (human or AI) needs must be in the repo:
- Current state: `docs/project-status.md`. Update it whenever a feature changes state.
- Decisions and rejected alternatives: `docs/adr/NNNN-title.md`.
- Open questions and known issues: listed in `docs/project-status.md`.
- Before starting a task, read `docs/project-status.md` and the relevant spec; at the end, update them.
