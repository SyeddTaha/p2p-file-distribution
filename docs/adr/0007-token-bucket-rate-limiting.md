# 0007. Token-bucket upload rate limiting

- Status: Accepted
- Date: 2026-11-19

## Context

Running benchmark experiments on local loopback (`127.0.0.1`) lacks the physical
bandwidth constraints of real networks. Without bandwidth bottlenecks, loopback
transfers complete nearly instantaneously regardless of whether distribution is
P2P or client-server, rendering speedup measurements meaningless.

To evaluate P2P scaling hypotheses under realistic, repeatable conditions, the
system requires a deterministic application-level upload rate limiter. In real
BitTorrent networks and university lab environments, each node's bottleneck is
typically its aggregate outbound upload capacity (uplink), shared across all
concurrent downloading peers.

## Decision

Implement `TokenBucketRateLimiter` in `src/p2p/peer/rate_limiter.py` and integrate
it into `SwarmPeer`:

1. **Shared per-node instance:** The rate limiter is owned by `SwarmPeer` and
   shared across all inbound serving connections. When serving a `REQUEST`,
   the peer acquires tokens for the chunk's byte length (`await self._rate_limiter.acquire(len(data))`)
   before transmitting the `PIECE` message.
2. **Token bucket parameters:**
   - `rate_bytes_per_sec`: Sustained bandwidth limit in bytes per second.
   - `burst_bytes`: Maximum accumulated token capacity (defaults to 1 second of rate).
3. **Handling oversized requests:** In chunked systems, a single chunk (e.g. 256 KiB)
   may exceed the burst allowance if the bandwidth cap is configured lower than the
   chunk size (e.g. 64 KiB/s). The limiter handles requests larger than burst capacity
   by calculating the required wait duration and sleeping proportionally, ensuring
   bandwidth invariants hold without deadlock.
4. **Deterministic testing:** An injectable monotonic clock (`clock: Callable[[], float]`)
   enables microsecond-level unit tests without wall-clock sleeps or test flakiness.
5. **Cancellation safety:** If a download connection disconnects or is cancelled while
   waiting for tokens, tokens are not deducted and accumulated time is preserved for
   other active connections.
6. **CLI integration:** Added `--upload-rate-limit <bytes/sec>` to both `seed-file`
   and `download-file` subcommands.

## Alternatives considered

- **Per-connection rate limiting:** Rejected because total upload capacity in a real
  host is bounded by the uplink interface; capping each connection independently would
  allow aggregate bandwidth to scale linearly with the number of connected leechers.
- **Sleep inside framing codec:** Rejected because low-level byte framing should have
  single responsibility (codec encoding/decoding) and remain agnostic of swarm-level
  bandwidth policy.
- **OS-level traffic shaping (tc / Mininet):** Rejected as a hard dependency because
  it is platform-specific (Linux-only), requires root/administrator privileges, and
  does not run portably on Windows development environments.

## Consequences

- Loopback experiments can simulate controlled asymmetric bandwidth environments
  (e.g., origin seeder cap of 1 MiB/s, leecher upload cap of 512 KiB/s).
- The limiter is optional: when omitted or set to `None`, transfers run unconstrained.
- Next deliverables for Milestone 8 are transfer metric counters and the automated
  experiment runner (`bench/run_experiments.py`).
