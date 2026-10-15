# 0003. Manifest v1 and Storage Integrity Policy

- Status: Accepted
- Date: 2026-10-15

## Context

Manifest and chunk data can arrive from untrusted peers. Milestone 3 needs
deterministic swarm identity, bounded validation, safe file placement, integrity
verification before accepting bytes, and atomic publication of complete files.

## Decision

Use the documented v1 JSON fields, SHA-256 lowercase hex digests, compact sorted-key
UTF-8 JSON for Swarm ID calculation, a 4 MiB manifest input cap, and a 30,000-chunk
cap. Empty files are unsupported in v1. The default chunk size remains the shared
256 KiB configuration value, bounded by the protocol maximum of 1 MiB.

Storage creates a fresh `.part` file, verifies chunk index, exact length, and SHA-256
before writing, does not overwrite verified chunks, and verifies the on-disk whole-file
digest before `os.replace`. A whole-file mismatch preserves the `.part` file for
diagnosis. Manifest JSON is written atomically in its destination directory.

## Alternatives considered

- Support empty files with zero chunks: rejected for v1 to keep the existing manifest
  count and storage completion rules simple; reconsider if a concrete use case needs it.
- Resume `.part` files using persisted bitfields: deferred because stored state cannot be
  trusted without rehashing each chunk and needs separate failure-mode tests.
- Use a database or third-party manifest format: rejected; the project uses JSON and
  standard-library hashing and filesystem operations.

## Consequences

The implementation is bounded and interoperable for non-empty files, but cannot
represent an empty file or resume a partial download. `StorageManager` is synchronous;
callers must serialize access when sharing an instance and keep large disk operations
off an event loop. Reserved Windows device names and symlink destinations are rejected
to keep output paths safe across supported platforms.
