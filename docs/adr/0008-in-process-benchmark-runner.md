# 0008. In-process controlled loopback benchmark runner

- Status: Accepted
- Date: 2026-11-20

## Context

Milestone 8 needs a portable, repeatable N=1,2,4,8 baseline/P2P comparison with
upload caps, raw client observations, failures and reproducible analysis.
The project already exposes `SwarmPeer` and injectable tracker transports.

## Decision

Run peers together with real loopback TCP and a fresh FastAPI tracker registry
via ASGI transport per trial. Use identical seeded source bytes, register all
clients before a common start, interleave seeded configuration order, record
one warmup and five measured trials per configuration, and append observations
after each trial. Set the scheduler RNG seed to the workload seed plus client
index, paired between modes; record the base and actual seeds. `SwarmPeer`
accepts an optional scheduler seed, preserving its existing default of zero.
Distinct seeds avoid forcing every client into identical chunk request order.

Record environment, source digest and dirty Git state. Keep repeated run-wide
upload totals explicit. Exclude whole unsuccessful/incomplete trials from
performance statistics, retain all raw rows, and generate a trial exclusion
audit with mean/sample-SD plots. See [methodology](../experiments.md).

## Alternatives considered

- Separate CLI processes and a socket-based tracker: closer to deployment,
  but would require a cross-process metrics collection interface and platform
  process management. Remains useful follow-up validation.
- Mock transfers: rejected because they would not measure actual framing,
  payload exchange, storage verification or rate limiting.
- Mininet: optional Linux-only infrastructure; unsuitable as a required runner.

## Consequences

No new dependencies or wire/tracker schema changes are needed. Trial resources
and ports are isolated and failure evidence remains inspectable. Results are
explicitly limited to shared-process loopback with an in-process tracker; they
cannot establish deployment or real-network performance.
