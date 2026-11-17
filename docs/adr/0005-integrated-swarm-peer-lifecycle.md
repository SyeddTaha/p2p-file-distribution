# 0005. Integrated Swarm Peer Lifecycle

- Status: Accepted
- Date: 2026-11-09

## Context

Milestone 6 provides a tested downloader for already-connected peers, but it
does not own tracker announcements, serve uploaded chunks, or keep a leecher
available after completion. The existing peer protocol has one ordered reader
per TCP connection, so idle HAVE messages must not compete with download workers
for socket reads.

## Decision

`SwarmPeer` owns one `PeerServer`, one HTTPX client, and a heartbeat task. It
announces `started`, uses the tracker-provided heartbeat interval, refreshes
discovery through `/announce`, announces `completed` after storage finalization,
and best-effort announces `stopped` during shutdown. Seeders verify the local
file by rebuilding and comparing its manifest before registration. Uploads read
only locally available chunks and recheck each chunk's length and hash before
sending.

For outbound connections, a dedicated reader task is the sole owner of socket
reads. It dispatches PIECE/HAVE messages through a bounded queue and updates
scheduler availability immediately on HAVE. The peer sends HAVE as verified
chunks arrive and advertises its updated bitfield to later inbound connections.
Inbound and outbound connections share the configured per-peer connection cap.
The CLI keeps seeders and completed downloaders alive until Ctrl+C.

## Alternatives considered

- **A seeder-only server and a one-shot downloader:** Rejected because downloaded
  peers would not serve already verified chunks during the transfer or remain
  available after completion.
- **Have every worker read the same connection:** Rejected because competing
  readers can consume another worker's PIECE/HAVE messages and corrupt request
  ownership.
- **Poll the tracker peer-list endpoint during transfers:** Rejected for the
  initial lifecycle; `/announce` already returns a bounded peer list and also
  refreshes the peer heartbeat. Full reconnect/discovery retry policies remain
  future work.

## Consequences

Peers can share verified partial files and participate as seeders after
completion, while keeping one reader per connection and bounded queues.
Discovery is refreshed when the download starts and on periodic heartbeats;
the downloader does not yet reconnect to newly announced peers after a transfer
has begun. Tracker state remains in-memory, and the CLI uses an advertised host
that must be reachable by other peers.
