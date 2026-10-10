---
name: p2p-distributed-systems
description: Design and implement the tracker (FastAPI HTTP control plane with in-memory state) and the peer-side swarm logic, including peer registration, heartbeats, stale-peer expiry, peer discovery, upload/download roles, chunk scheduling, parallel downloads, duplicate-work avoidance, retries, peer failure handling, cancellation, bounded concurrency, and state ownership. Use when working on tracker endpoints, swarm membership, or the download scheduler. Not for byte-level framing, manifest and disk integrity, test strategy, or benchmark methodology.
---

# P2P Distributed Systems

## When to use / when not to use

Use when designing or changing:
- tracker endpoints, peer registry, heartbeat/expiry logic, peer lists;
- the peer's download scheduler, peer selection, retry/failover, cancellation, concurrency limits;
- who owns which piece of mutable state, and how races are avoided.

Do **not** use for:
- message encoding, framing, handshake bytes, socket read timeouts -> `tcp-protocol-engineering`
- hash verification, manifest, temp files, reconstruction -> `chunk-storage-integrity`
- test harness design -> `network-testing-reliability`
- measurement design -> `network-benchmarking`

## Keep it simple (primary constraint)

This is a course project. Prefer the simplest design that is correct and measurable. Do not add DHT, choking/tit-for-tat, NAT traversal, gossip, or consensus. Tracker state is in memory and may be lost on restart; peers simply re-announce. If you believe more complexity is needed, write an ADR first.

## Tracker responsibilities

The tracker is a **directory, not a data path**. It never relays chunks.

Suggested HTTP interface (a proposal; finalize it in `docs/architecture.md` and test it):
- `POST /announce` with body `{swarm_id, peer_id, host, port, event}` where `event` is `started | heartbeat | completed | stopped`. Returns the current peer list for the swarm (excluding the caller) and the heartbeat interval.
- `GET /swarms/{swarm_id}/peers` returns peers (`peer_id, host, port, last_seen, is_seeder`).
- `GET /health` for tests and scripts.

Behaviors:
- **Registration:** `started` creates or refreshes a peer record keyed by `(swarm_id, peer_id)`.
- **Heartbeat:** refreshes `last_seen` from an *injected monotonic clock* (a small `Clock` object), not from `time`/`datetime` calls scattered in handlers.
- **Stale expiry:** a peer not seen for `3 x heartbeat_interval` (suggested) is removed, by a background task or lazily on read. Pick one, document it, and make it deterministic in tests with the fake clock.
- **Validation:** `swarm_id` is 64 lowercase hex chars; `port` in 1..65535; `peer_id` bounded in length and charset; cap peers per swarm and cap the list returned (e.g. a random sample of at most 50).
- **Idempotency:** repeated `started`/`stopped` for the same peer is safe.
- The tracker does not verify that peers really have the file; peers verify every chunk by hash (`chunk-storage-integrity`).
- Use the peer's *advertised* `host`/`port` consistently; decide in an ADR whether the tracker trusts the advertised host or uses the observed client address (observed address is safer on a LAN).

## Peer roles

A peer is an uploader and a downloader at once. A **seeder** has all chunks; a **leecher** is missing some. A leecher serves chunks it has already verified (announced via BITFIELD/HAVE). Role is derived from the local bitfield, not from a separate flag, except at start-up when the initial seeder loads a complete, verified file.

## State ownership (avoid races)

Asyncio is single-threaded, so races appear only across `await` points. Rules:
- One owner per piece of state. Suggested owners:
  - **Tracker registry:** owned by the tracker service; mutated only through its methods.
  - **Local chunk status/bitfield:** owned by the scheduler; connection tasks call into it, they do not mutate it directly.
  - **Per-connection state** (remote bitfield, outstanding requests): owned by that connection object.
- Never do check-then-act across an `await` without re-checking. Either reserve synchronously before awaiting (mark `IN_FLIGHT` immediately) or re-check after.
- Chunk states: `MISSING -> IN_FLIGHT(peer) -> VERIFIED`, and back to `MISSING` on failure, timeout, or hash mismatch. Only the storage layer, after hash verification, may cause `VERIFIED`.

## Download scheduling workflow

1. Announce to the tracker, get peers, connect to at most `MAX_PEER_CONNECTIONS`.
2. Maintain each remote bitfield (BITFIELD, then HAVE updates).
3. Pick the next chunk among `MISSING` chunks that at least one connected peer has. A simple policy (sequential or random with a seedable RNG) is acceptable; **rarest-first** is an optional improvement. Whichever you choose, document it and make it reproducible (seeded RNG).
4. Reserve the chunk (`IN_FLIGHT`) *before* sending REQUEST, so two connections never fetch the same chunk. (End-game duplicate requests are out of scope unless documented.)
5. Bound concurrency: global in-flight (`MAX_INFLIGHT`), per-peer in-flight (`MAX_INFLIGHT_PER_PEER`, small), total connections.
6. On PIECE: pass to storage for verification. Success -> `VERIFIED`, broadcast HAVE. Failure -> `MISSING`, strike against that peer.
7. Retries: per-chunk attempt cap with backoff; prefer a *different* peer on retry.
8. Peer failure (disconnect, timeout, protocol violation, repeated bad chunks): release its `IN_FLIGHT` chunks, close the connection, ignore the peer for a cool-down, refresh the peer list.
9. Completion: all chunks `VERIFIED` -> full-file verification and final rename (`chunk-storage-integrity`) -> announce `completed` -> continue as seeder.
10. Terminal failure: if the tracker is unreachable or no peer has a needed chunk, retry with backoff up to a limit, then fail with a clear error. No infinite loops.

## Concurrency and cancellation

- Use `asyncio.TaskGroup` or explicitly tracked tasks. Every task has an owner and is cancelled and awaited on shutdown.
- Use `asyncio.Semaphore` or bounded queues for limits; never spawn one unbounded task per chunk.
- Never swallow `CancelledError`. In `finally`, release reserved chunks and close connections.
- Shutdown order: stop accepting new work -> cancel workers -> await them -> release chunk reservations -> close sockets -> send `stopped` to the tracker (best effort, with timeout).

```python
async def worker(conn, scheduler):
    try:
        while (idx := scheduler.reserve_next_for(conn)) is not None:
            try:
                data = await conn.request_chunk(idx)  # has its own timeout
            except (TimeoutError, ConnectionError, ProtocolError):
                scheduler.release(idx, conn.peer_id, failed=True)
                return
            scheduler.complete(idx, data)  # storage verifies; may release on bad hash
    finally:
        scheduler.release_all_for(conn.peer_id)  # runs on cancellation too
```

This is an illustrative sketch of the intended shape, not a final API. `ProtocolError` is defined by the protocol layer.

## Common failure modes

- Two connections requesting the same chunk because reservation happened after an `await`.
- A dead peer holding chunks `IN_FLIGHT` forever.
- Unbounded retries or retry storms hammering one peer or the tracker.
- Stale peers listed because expiry is never triggered.
- Tracker returning the caller to itself; duplicate connections between the same pair of peers.
- Heartbeat tasks leaking after `stopped`.
- Tests that rely on real `sleep` for expiry instead of an injected clock.
- Scheduler stuck on one slow peer because per-peer limits are missing.

## Checklist

- [ ] State owners are documented in `docs/architecture.md`.
- [ ] All concurrency limits are named constants and documented.
- [ ] Expiry and heartbeats use an injectable clock.
- [ ] Each failure path (disconnect, timeout, bad chunk, no peers, tracker down) has defined behavior and a test.
- [ ] Shutdown/cancellation leaves no tasks or open sockets.
- [ ] No component other than storage causes a chunk to become `VERIFIED`.

## Validation requirements

Apply `network-testing-reliability` patterns: multi-peer integration tests on loopback with ephemeral ports; a slow peer, a disconnecting peer, a peer serving corrupt data; tracker expiry via fake clock. Tests must show no duplicate in-flight chunk and no leaked tasks.

## Expected deliverables and documentation updates

Tracker and peer-orchestration code; `docs/architecture.md` (components, state ownership, download sequence, failure behavior, tracker endpoints); ADRs for scheduling policy and expiry design; updated `docs/project-status.md`.
