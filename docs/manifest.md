# Manifest Specification

*(See the primary specification in [manifest-format.md](./manifest-format.md).)*

## Reference Schema Summary

```json
{
  "manifest_version": 1,
  "file_name": "example.bin",
  "file_size": 1048576,
  "chunk_size": 262144,
  "chunk_count": 4,
  "file_sha256": "<64 hex chars>",
  "chunks": [
    { "index": 0, "length": 262144, "sha256": "<64 hex chars>" }
  ]
}
```

- **Swarm ID:** `sha256(canonical_json_bytes)` using compact separators `,` and `:` with sorted keys.
- **Manifest output:** `write_manifest()` validates and atomically writes UTF-8 JSON.
- **Safety:** Path traversal prevention enforced via `validate_safe_filename()`.
- **Integrity:** SHA-256 verified per chunk before disk acceptance; whole-file SHA-256 verified before atomic `.part` rename.
- **Limits:** 4 MiB maximum encoded manifest size, 30,000 chunks maximum, 1 MiB maximum chunk size; empty files are unsupported.
