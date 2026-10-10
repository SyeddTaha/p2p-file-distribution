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
  "file_size": 1048576,
  "chunk_size": 262144,
  "chunk_count": 4,
  "file_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "chunks": [
    {
      "index": 0,
      "length": 262144,
      "sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    },
    {
      "index": 1,
      "length": 262144,
      "sha256": "4813474d722141454e737596bf5176478330664ce4990c76899e4b65103d002e"
    },
    {
      "index": 2,
      "length": 262144,
      "sha256": "9b74c9897bac770ffc029102a200c5de3c730b182fbda19b5d997e74c4d94ae7"
    },
    {
      "index": 3,
      "length": 262144,
      "sha256": "5058f1af8388633f609cadb75a75dc9d08dd856f3630f90c427845348bb95b2c"
    }
  ]
}
```

---

## 3. Field Specifications & Constraints

| Field Name | Type | Constraints | Description |
|---|---|---|---|
| `manifest_version` | `integer` | Must equal `1` | Schema version identifier |
| `file_name` | `string` | Safe filename (1..255 chars, no path separators or escape characters) | Display filename for reconstruction |
| `file_size` | `integer` | `>= 1` bytes (empty files not supported in v1) | Total file size in bytes |
| `chunk_size` | `integer` | `1 .. 1048576` (1 byte to 1 MiB). Default: `262,144` (256 KiB) | Nominal size of each chunk |
| `chunk_count` | `integer` | Must equal `ceil(file_size / chunk_size)` | Total number of chunks |
| `file_sha256` | `string` | Exactly 64 lowercase hex characters | SHA-256 hash of entire file |
| `chunks` | `array` | Length MUST equal `chunk_count` | List of chunk descriptors |
| `chunks[i].index` | `integer` | Exactly `0 .. chunk_count - 1` in order | Zero-based chunk index |
| `chunks[i].length` | `integer` | `chunk_size` for `0..n-2`, `file_size - (n-1)*chunk_size` for `n-1` | Chunk byte length |
| `chunks[i].sha256` | `string` | Exactly 64 lowercase hex characters | SHA-256 hash of chunk payload |

---

## 4. Swarm ID Derivation

The **Swarm ID** is a 64-character lowercase hex string computed by taking the SHA-256 hash of the **canonical JSON representation** of the manifest object:

```python
import json
import hashlib

def compute_swarm_id(manifest_dict: dict) -> str:
    canonical_bytes = json.dumps(
        manifest_dict,
        sort_keys=True,
        separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest().lower()
```

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
    target_path = (base_dir / file_name).resolve()
    
    if target_path.parent != base_dir:
        raise ValueError("Path escapes download directory")
        
    return target_path
```

---

## 6. Verification Workflow

1. **Chunk Verification:** When a piece is received over TCP, compute its SHA-256 digest before writing to `<filename>.part`. If `sha256(received_data) != manifest.chunks[index].sha256`, reject the piece immediately.
2. **Whole-File Verification:** When all chunks are verified and stored in `<filename>.part`, calculate `sha256(file_on_disk)`. If it matches `file_sha256`, execute atomic rename (`os.replace`) to the final target filename.
