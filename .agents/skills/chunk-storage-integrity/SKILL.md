---
name: chunk-storage-integrity
description: Define and implement the JSON file manifest, chunking, SHA-256 chunk and whole-file verification, safe file paths, temporary files, atomic reconstruction, and corruption handling for the P2P system, treating all remote peer data as untrusted. Use when working on manifest creation/parsing, chunk validation before acceptance, disk writes, reassembly, or resume support. Not for wire framing, tracker or scheduling logic, test strategy, or benchmark design.
---

# Chunk Storage and Integrity

## When to use / when not to use

Use when working on:
- manifest format, creation, parsing, and validation;
- splitting a file into chunks, hashing, verifying chunks and the final file;
- writing chunks to disk, temporary files, final reconstruction, path safety;
- handling corrupted or inconsistent data; optional resume support.

Do **not** use for:
- how bytes are framed on the socket -> `tcp-protocol-engineering`
- which peer to ask for which chunk, retries across peers -> `p2p-distributed-systems`
- test infrastructure -> `network-testing-reliability` (this skill defines *what* must be verified)

## Core principle: remote data is untrusted

A peer can send wrong, truncated, oversized, or malicious bytes. A chunk is accepted **only** after: the index is in range, the length equals the manifest length for that index, and its SHA-256 equals the manifest hash. Only then is it persisted and marked verified. The manifest itself is also untrusted input until validated.

## Reference manifest format (v1)

Update `docs/manifest.md` with any change. Proposed JSON:

```json
{
  "manifest_version": 1,
  "file_name": "example.bin",
  "file_size": 1048576,
  "chunk_size": 262144,
  "chunk_count": 4,
  "file_sha256": "<64 lowercase hex>",
  "chunks": [
    {"index": 0, "length": 262144, "sha256": "<64 hex>"}
  ]
}
```

Rules to validate on load (reject on any violation, with a specific error):
- `manifest_version` is supported; all required fields present with correct types (no bools-as-ints).
- `chunk_size` in `1..MAX_CHUNK_SIZE` (shared constant with the protocol layer).
- `chunk_count == ceil(file_size / chunk_size)`; `len(chunks) == chunk_count`; indices are exactly `0..n-1` in order.
- Every chunk `length == chunk_size`, except the last which is `file_size - (n-1)*chunk_size`; sum of lengths equals `file_size`.
- Hashes are 64 lowercase hex characters.
- `file_size == 0` policy is decided and documented (either reject or allow with `chunk_count == 0`).
- Total manifest size and `chunk_count` are capped before parsing into memory (e.g. reject manifests > a few MiB).
- `file_name` is a plain base name (see safe paths).

**Swarm ID:** `swarm_id = sha256(canonical_manifest_bytes)` where canonical bytes are the UTF-8 JSON with sorted keys and compact separators (`json.dumps(obj, sort_keys=True, separators=(",", ":"))`). Document this precisely so two implementations agree. This value is what HANDSHAKE and the tracker use to identify the swarm.

## Safe paths

`file_name` comes from a manifest and may be hostile (`../../x`, absolute paths, `C:\`, NUL bytes, reserved Windows names, very long names, empty).
- Accept only a non-empty base name: no `/`, `\`, NUL, `..`, no leading drive letter; length-capped.
- Always build the target as `download_dir / name`, then `resolve()` and assert the result's parent is the resolved download dir (`Path.is_relative_to`).
- Teammates may use Windows, macOS, or Linux: never hard-code absolute paths or assume `/`.

```python
from pathlib import Path

def safe_target(download_dir: Path, file_name: str) -> Path:
    if (not file_name or len(file_name) > 255 or file_name in {".", ".."}
            or any(c in file_name for c in ("/", "\\", "\x00", ":"))):
        raise ValueError("unsafe file name")
    base = download_dir.resolve()
    target = (base / file_name).resolve()
    if target.parent != base:
        raise ValueError("path escapes download directory")
    return target
```

## Hashing

```python
import hashlib

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
```

- For large files, hash incrementally (`hashlib.sha256()` + `update()` over fixed-size reads), never `read()` the whole file.
- Large hashing or disk I/O must not block the event loop for long: use bounded chunk sizes and/or `asyncio.to_thread`.
- Compare hex digests normalized to lowercase.

## Storage and reconstruction workflow

1. **Create manifest** (seeder side script): stream the file, compute per-chunk and whole-file hashes, write manifest atomically.
2. **Prepare download:** validate manifest, compute `safe_target`, create `<name>.part` (temporary) in the *same directory* as the final file. Preallocate (optional) to `file_size`.
3. **Accept a chunk:** check index range, check `len(data) == manifest.chunks[i].length`, check hash. Only then `write` at offset `index * chunk_size` to the `.part` file and mark verified.
4. **Idempotency:** a chunk already verified is never overwritten; duplicate deliveries are dropped.
5. **Finalize:** when all chunks are verified, flush/fsync, recompute the **whole-file SHA-256** from disk, compare to `file_sha256`; on success `os.replace(part, final)` (atomic on the same filesystem); on failure keep/rename the part for diagnosis and report an error.
6. **Serve chunks:** read from the final file (or `.part` for verified chunks only) at the correct offset and exact length; never serve unverified bytes.
7. **Resume (later, optional):** only after basic transfer is reliable and tested. On start, re-hash existing `.part` data against the manifest to rebuild the verified bitfield; never trust a stored bitfield blindly. Needs its own ADR and tests.

## Corruption handling

- Hash mismatch on a chunk: discard bytes, report to the scheduler (which strikes the peer and retries elsewhere). Do not write the bytes to disk.
- Whole-file mismatch after all chunks verified: indicates a manifest inconsistency or local disk corruption; fail loudly, keep diagnostics, do not publish the final file.
- Manifest/file size mismatch for a seeder's local file: refuse to seed; report clearly.
- Disk errors (full disk, permission): surface as explicit errors; clean up the `.part` file only when the policy says so, and document that policy.

## Common failure modes

- Trusting `file_name` or any manifest field without validation.
- Checking the hash but not the length (or length but not index range).
- Writing the chunk before verifying it.
- Wrong offset for the last, shorter chunk; off-by-one in `chunk_count`.
- Non-atomic finalization leaving a partial file with the final name.
- Opening the file in text mode; forgetting `seek` vs. positional writes under concurrency (serialize writes through one owner or use `os.pwrite`/`asyncio.to_thread`).
- Whole-file hash computed from memory instead of from the file on disk.
- Resume that trusts stale metadata.
- Manifest hashes computed over text with newline conversions instead of raw bytes.

## Checklist

- [ ] `docs/manifest.md` matches the code, including swarm ID derivation.
- [ ] Manifest validator has tests for each validation rule above.
- [ ] Chunk acceptance tests: wrong index, wrong length, wrong hash, duplicate, valid.
- [ ] Path safety tests: `..`, absolute, backslash, drive letter, NUL, empty, overlong.
- [ ] Final-file verification and atomic rename tested, including the failure path.
- [ ] Edge sizes tested: empty file (per policy), 1 byte, exactly one chunk, exact multiple of chunk size, multiple + remainder.
- [ ] No unverified bytes are ever served to peers.

## Validation requirements

Pure-function tests for manifest validation and chunk acceptance; `tmp_path` based tests for disk behavior; corruption tests that flip a byte and truncate data. Follow `network-testing-reliability` for fixtures and reporting.

## Expected deliverables and documentation updates

Manifest builder/validator, storage module, finalize/verify logic; `docs/manifest.md` (schema, validation rules, swarm ID derivation, size limits); an ADR for chunk size default, resume policy, or empty-file policy; updated `docs/project-status.md`.
