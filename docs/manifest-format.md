# File Manifest & Integrity Specification (v1)

## 1. Overview

A file manifest is a structured JSON document that describes a shared file, its chunking parameters, and cryptographic SHA-256 integrity digests for both individual chunks and the overall file.

Every swarm in the P2P network is uniquely identified by its **Swarm ID**, which is deterministically derived from its manifest content.

---

## 2. Manifest Schema (JSON)

```json
{
  "manifest_version": 1,
  "file_name": "sample_dataset.bin",
  "file_size": 10,
  "chunk_size": 4,
  "chunk_count": 3,
  "file_sha256": "72399361da6a7754fec986dca5b7cbaf1c810a28ded4abaf56b2106d06cb78b0",
  "chunks": [
    {
      "index": 0,
      "length": 4,
      "sha256": "88d4266fd4e6338d13b845fcf289579d209c897823b9217da3e161936f031589"
    },
    {
      "index": 1,
      "length": 4,
      "sha256": "e5e088a0b66163a0a26a5e053d2a4496dc16ab6e0e3dd1adf2d16aa84a078c9d"
    },
    {
      "index": 2,
      "length": 2,
      "sha256": "c9df9c3f2963b19b9b95f58c4d33b053fa9f8586dd6ee04126e52a868f882108"
    }
  ]
}
```

The example represents the ten raw bytes `abcdefghij`, split into 4-byte chunks.

---

## 3. Field Specifications & Constraints

| Field Name | Type | Constraints | Description |
|---|---|---|---|
| `manifest_version` | `integer` | Must equal `1` | Schema version identifier |
| `file_name` | `string` | Safe filename (1..255 chars; no separators, NUL, drive prefixes, `.`/`..`, trailing spaces/dots, or reserved Windows device names; destination cannot be a symlink) | Display filename for reconstruction |
| `file_size` | `integer` | `>= 1` bytes (empty files not supported in v1) | Total file size in bytes |
| `chunk_size` | `integer` | `1 .. 1048576` (1 byte to 1 MiB). Default: `262,144` (256 KiB) | Nominal size of each chunk |
| `chunk_count` | `integer` | Must equal `ceil(file_size / chunk_size)` | Total number of chunks |
| `file_sha256` | `string` | Exactly 64 lowercase hex characters | SHA-256 hash of entire file |
| `chunks` | `array` | Length MUST equal `chunk_count` | List of chunk descriptors |
| `chunks[i].index` | `integer` | Exactly `0 .. chunk_count - 1` in order | Zero-based chunk index |
| `chunks[i].length` | `integer` | `chunk_size` for `0..n-2`, `file_size - (n-1)*chunk_size` for `n-1` | Chunk byte length |
| `chunks[i].sha256` | `string` | Exactly 64 lowercase hex characters | SHA-256 hash of chunk payload |

The v1 validator rejects unknown or missing fields, booleans where integers are
required, and duplicate JSON object keys. Empty files are unsupported. JSON input is
limited to 4 MiB and manifests are limited to 30,000 chunks. Chunk sizes are bounded by
the protocol's `MAX_CHUNK_SIZE` (1 MiB).

---

## 4. Swarm ID Derivation

The **Swarm ID** is a 64-character lowercase hex string computed by taking the SHA-256 hash of the **canonical JSON representation** of the manifest object:

```python
import json
import hashlib
from p2p.storage.manifest import validate_manifest

def compute_swarm_id(manifest_dict: dict) -> str:
    validated_manifest = validate_manifest(manifest_dict)
    canonical_bytes = json.dumps(
        validated_manifest,
        sort_keys=True,
        separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()
```

Canonicalization is applied to the validated v1 object, with its required field names
and values, using UTF-8 JSON, lexicographically sorted object keys, and no whitespace.
The resulting Swarm ID is the lowercase 64-character SHA-256 hex digest.

---

## 5. Safe Filename Validation

To prevent directory traversal and path manipulation attacks, all `file_name` values must pass the following checks:

```python
from pathlib import Path

def validate_safe_filename(download_dir: Path, file_name: str) -> Path:
    if not file_name or len(file_name) > 255 or file_name in {".", ".."}:
        raise ValueError("Invalid file name")
    if any(char in file_name for char in ("/", "\\", "\x00", ":")):
        raise ValueError("Forbidden characters in file name")
    
    base_dir = download_dir.resolve()
    candidate = base_dir / file_name
    target_path = candidate.resolve()
    
    if target_path != candidate:
        raise ValueError("Destination filename must not be a symbolic link")
    if target_path.parent != base_dir:
        raise ValueError("Path escapes download directory")
        
    return target_path
```

In addition to the checks shown, the implementation rejects names ending in a dot or
space and Windows reserved device basenames such as `CON`, `NUL`, and `COM1`.

---

## 6. Verification Workflow

1. **Chunk Verification:** `StorageManager.write_chunk()` validates the index, exact length, and SHA-256 before writing to `<filename>.part`. Invalid data raises `ChunkIntegrityError`; a duplicate verified index is ignored and is never overwritten.
2. **Whole-File Verification:** `StorageManager.finalize()` refuses incomplete downloads, hashes the `.part` file from disk, and only calls `os.replace` after the digest matches. An incomplete or mismatched file is not published; a whole-file mismatch leaves the `.part` file for diagnosis.

`write_manifest()` validates the object and atomically writes compact UTF-8 JSON via a
temporary file in the destination directory. The storage API is synchronous and intended
for bounded chunk operations. Callers sharing a `StorageManager` between concurrent
workers must serialize its operations. Construction starts a fresh download by
truncating any prior `.part` file; resume support is not implemented.
