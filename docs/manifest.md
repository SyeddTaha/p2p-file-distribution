# Manifest Specification

*(See primary specification in [`docs/manifest-format.md`](file:///c:/Users/tahaj/OneDrive%20-%20FAST%20National%20University/5th%20Sem%20CN/p2p-file-distribution/docs/manifest-format.md))*

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
- **Safety:** Path traversal prevention enforced via `validate_safe_filename()`.
- **Integrity:** SHA-256 verified per chunk before disk acceptance; whole-file SHA-256 verified before atomic `.part` rename.
