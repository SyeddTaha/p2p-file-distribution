# 0006. Download-only client-server baseline

- Status: Accepted
- Date: 2026-11-19

## Context

The benchmark plan compares the same transfer implementation with and without
leecher uploads. Disabling only the listener's PIECE responses would leave
BITFIELD/HAVE advertising unusable sources. HAVE can be emitted by both
`SwarmPeer` and `SwarmDownloader`, including to existing outbound connections.

## Decision

Add a per-instance `SwarmPeer(upload_enabled=False)` option and expose it as
`download-file --no-upload`. Normal P2P uploading remains enabled by default.
For the client-server baseline, every downloading client uses this option and
the single original seed keeps uploading enabled. The tracker remains a
directory with the existing schema; no global mode switch is needed.

A download-only peer always advertises an empty BITFIELD, suppresses HAVE on
inbound and outbound connections, and closes a connection that requests a chunk
without reading or sending its contents. This policy persists after completion.
`SwarmDownloader(advertise_chunks=False)` suppresses its own HAVE broadcasts
while retaining verified-chunk callbacks. Chunk storage, scheduler selection,
integrity verification, finalization, and lifecycle announcements are shared.

`is_seeder` continues to mean local file completeness, including in tracker
announcements. It is not an upload-capability flag; actual chunk availability
comes from BITFIELD/HAVE. Completed clients remain online until closed, just
as P2P clients do, and continue heartbeat/completed/stopped lifecycle handling.

## Alternatives considered

- A separate whole-file server/client: rejected because it would change framing,
  chunking, and integrity costs between modes.
- A tracker-wide baseline flag or filtering by `is_seeder`: rejected because
  uploading is owned by peers and completed download-only clients also have the
  complete file. A tracker flag would require extra shared configuration.
- Suppress only PIECE: rejected because peers would still advertise chunks and
  attract requests they cannot fulfill.

## Consequences

Correctness tests can compare origin-only transfers with normal P2P transfers.
Every client must opt out of uploading for an origin-only experiment; mixed
swarms may still contain other uploading peers. Download-only peers retain
listeners and can consume connection slots, so this is a controlled experiment
mode, not a new wire protocol or an access-control mechanism.

This change is only the baseline prerequisite. Shared per-uploader token-bucket
limits, transfer metrics, the workload runner, CSV collection, and plots remain
planned. Unconstrained loopback correctness tests are not performance evidence.
