---
name: network-testing-reliability
description: Plan, write, and review automated tests for the P2P networking system using pytest and pytest-asyncio, including unit, integration, and end-to-end tests, deterministic fixtures, temporary directories, loopback sockets with ephemeral ports, malformed protocol messages, slow peers, disconnects, timeouts, retries, corrupted chunks, cancellation, and resource cleanup. Use when adding tests, debugging flaky tests, or reporting test results. Not for defining the protocol, manifest, or scheduling behavior themselves, and not for performance benchmarking.
---

# Network Testing and Reliability

## When to use / when not to use

Use when:
- writing or reviewing tests for any component;
- building fixtures, fake peers, or fault-injection helpers;
- diagnosing flaky or hanging tests;
- reporting what was tested and what passed.

Do **not** use for:
- deciding what the protocol, manifest, or scheduler *should* do -> the owning skill (`tcp-protocol-engineering`, `chunk-storage-integrity`, `p2p-distributed-systems`)
- performance measurement and plots -> `network-benchmarking` (tests assert correctness, not speed)
- test documentation structure -> `engineering-documentation` (this skill supplies content for `docs/testing.md`)

## Ground rules

- **No external Internet.** Tests use `127.0.0.1` only. Bind servers to port `0` and read the assigned port from the socket.
- **Deterministic.** Seed any RNG; inject clocks; generate test data from a seeded `random.Random(seed).randbytes(n)`. No dependence on wall-clock sleeps for logic (use events, fake clocks, or very short bounded timeouts).
- **Isolated.** Use `tmp_path`; never write to the repo tree or home directory. No shared global state between tests.
- **Bounded.** Every async test has a timeout so a hang fails instead of freezing CI (`asyncio.timeout(...)` inside tests, or a pytest timeout plugin only if the team approves the dependency).
- **Clean.** Tests close all sockets/servers and leave no pending tasks.
- **Honest reporting.** Report only what was run. Quote the command and the outcome. If a test was skipped, flaky, or not run, say so.

## Test pyramid for this project

| Level | Scope | Examples |
|---|---|---|
| Unit | Pure logic, no sockets | frame codec round-trips, manifest validation, chunk acceptance, scheduler decisions, tracker registry with fake clock |
| Integration | Real loopback sockets, 2-3 components | handshake between two peers, tracker HTTP via FastAPI `TestClient`/ASGI transport, one leecher + one seeder |
| End-to-end | Full system on loopback | tracker + seeder + N leechers download a temp file and every final SHA-256 matches |

Most tests should be unit tests; keep end-to-end tests few, stable, and fast.

## Setup notes

- `pytest-asyncio`: configure `asyncio_mode = "auto"` in `pyproject.toml` (or mark tests with `@pytest.mark.asyncio`). Pick one convention and document it in `docs/testing.md`.
- Fixtures: `tmp_path`, a `sample_file` fixture (seeded bytes of chosen size), a `manifest` fixture, a `running_tracker` fixture and a `start_peer` factory fixture that registers cleanup.
- Prefer real loopback sockets over mocking `asyncio` streams for protocol tests; use mocks/fakes only for things that are slow or nondeterministic (clock, RNG, a fake peer implementing the protocol with scripted behavior).

```python
import asyncio
import pytest

@pytest.fixture
async def echo_server():
    async def handler(reader, writer):
        data = await reader.read(1024)
        writer.write(data)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield "127.0.0.1", port
    finally:
        server.close()
        await server.wait_closed()
```

(With `asyncio_mode = "auto"` async fixtures work directly; in strict mode use `@pytest_asyncio.fixture`.)

## Fault-injection toolkit (build as small helpers under `tests/helpers/`)

- **Scripted fake peer:** speaks the real protocol but can: stall mid-frame, send one byte at a time, send two frames in one write, send oversize length, send bad type, send a corrupt PIECE, send a wrong-length PIECE, never answer a REQUEST, close mid-transfer, reset the connection.
- **Slow peer:** inserts `await asyncio.sleep(...)` with small values and uses short configured timeouts so tests stay fast.
- **Fake clock:** for tracker expiry and heartbeat behavior.
- **Resource checks:** after each test assert no leftover tasks (`asyncio.all_tasks()` minus current) and no unclosed servers; surface `ResourceWarning`s as errors in pytest config where practical.

## Required scenarios (mapped to owners)

Protocol (`tcp-protocol-engineering`): round-trips; split delivery; merged delivery; zero/oversize length; truncated header and body; unknown type; wrong fixed size; bad JSON handshake; version mismatch; unsolicited PIECE; out-of-range index; bad BITFIELD.

Storage (`chunk-storage-integrity`): manifest rule violations; bad hash/length/index chunks; duplicate chunk; path traversal names; final hash mismatch; atomic finalize; edge sizes.

Swarm (`p2p-distributed-systems`): tracker registration, heartbeat, expiry, invalid input, idempotent `stopped`; no duplicate in-flight chunk; peer disconnect mid-chunk -> reassigned; slow peer does not block others; corrupt chunk -> retry from another peer; no peers available -> bounded failure; cancellation releases reservations and closes sockets.

End-to-end: seeder + 2-3 leechers, all files byte-identical to the original, hashes verified, clean shutdown.

## Workflow

1. Write the failing test first for bug fixes; for features, write unit tests alongside the code.
2. Run the narrowest test first (`pytest path::test_name`), then the full suite.
3. Run `ruff check .` and `mypy` (where configured). Treat warnings that indicate un-awaited coroutines or unclosed resources as failures.
4. Run the suite several times (e.g. 5 repetitions) before claiming a network test is stable; if flaky, find the race, do not add arbitrary sleeps.
5. Record results honestly in the PR description and `docs/project-status.md`.

## Common failure modes

- Fixed ports causing collisions between tests or machines.
- `sleep`-based synchronization that passes locally and fails on slower machines.
- Tests that pass because exceptions are swallowed inside tasks nobody awaits.
- Leaked servers/tasks causing cross-test interference.
- Asserting on timing precision instead of behavior.
- Mocking so much that the test no longer exercises real framing or real sockets.
- Testing only the happy path.
- Claiming "all tests pass" without running them in the current state of the code.

## Checklist

- [ ] No Internet access, no fixed ports, no writes outside `tmp_path`.
- [ ] Seeds/clock injected; tests reproducible across runs.
- [ ] Every async test is time-bounded.
- [ ] Each fault scenario above relevant to the change has a test.
- [ ] Cleanup verified (no leaked tasks/sockets).
- [ ] Results reported with exact commands and outcomes, including failures and skips.

## Expected deliverables and documentation updates

Tests under `tests/unit`, `tests/integration`, `tests/e2e`; shared fixtures/helpers; `docs/testing.md` (how to run, conventions, scenario matrix, known flaky tests); `docs/project-status.md` updated with *actual* test state (what exists, what was last run and the result).
