# 0004. Download Scheduling and Peer Failover

- Status: Accepted
- Date: 2026-11-09

## Context

Milestone 6 needs to coordinate chunk requests across connected peers without
duplicate work, unbounded concurrency, or accepting unverified data. The peer
connection protocol carries chunk indices in each `PIECE`, but each connection
object has one receive stream owner; adding parallel reads per connection would
require a separate response-dispatch mechanism.

## Decision

`DownloadScheduler` selects a seeded random chunk from the selected peer's
available missing chunks. It reserves synchronously before network I/O.
`SwarmDownloader` runs at most one `DownloadWorker` per connected peer at once,
with at most one outstanding request on each connection. Total connections and
global in-flight requests are bounded by `MAX_PEER_CONNECTIONS` and
`MAX_GLOBAL_INFLIGHT`.

The worker requires `StorageManager`; it marks a chunk verified only after
storage accepts the chunk hash and length. It keeps a reservation while retrying
the current peer, then releases it and retires the peer after retry exhaustion.
The coordinator can then assign the missing chunk to another peer. Cancellation
releases reservations, closes owned connections, and propagates cancellation.
Verified chunks are announced to the other active connections with `HAVE`.

## Alternatives considered

- **Rarest-first scheduling:** Rejected for this milestone because seeded random
  selection is simpler and reproducible; peer scarcity optimization can be
  evaluated later if needed.
- **Multiple requests in flight per connection:** Deferred because safe
  concurrent reads require a dedicated message dispatcher and per-request
  response correlation. One request per peer keeps ownership and cleanup simple.
- **Retry the same peer indefinitely or keep a failed peer active:** Rejected;
  retries have a fixed attempt limit and an exhausted peer is removed so other
  peers can provide its outstanding chunks.

## Consequences

The coordinator can download concurrently across peers but does not pipeline
requests to a single peer. It accepts already-established connections and does
not query the tracker, start a seeder, or provide CLI commands; those belong to
Milestone 7. A failed peer is retired for the current download rather than
placed on a timed cooldown.
