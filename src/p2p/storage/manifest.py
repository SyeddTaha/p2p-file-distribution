"""Manifest creation, validation, parsing, and swarm identity."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import TypedDict

from p2p.config import DEFAULT_CHUNK_SIZE, MAX_CHUNK_SIZE

MANIFEST_VERSION = 1
MAX_MANIFEST_SIZE = 4 * 1024 * 1024
MAX_CHUNK_COUNT = 30_000
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_MANIFEST_FIELDS = {
    "manifest_version",
    "file_name",
    "file_size",
    "chunk_size",
    "chunk_count",
    "file_sha256",
    "chunks",
}
_CHUNK_FIELDS = {"index", "length", "sha256"}


class ChunkDescriptor(TypedDict):
    index: int
    length: int
    sha256: str


class FileManifest(TypedDict):
    manifest_version: int
    file_name: str
    file_size: int
    chunk_size: int
    chunk_count: int
    file_sha256: str
    chunks: list[ChunkDescriptor]


class ManifestError(ValueError):
    """Raised when a manifest is malformed or violates the v1 schema."""


def _validate_file_name(file_name: object) -> str:
    if not isinstance(file_name, str):
        raise ManifestError("file_name must be a string")
    if (
        not file_name
        or len(file_name) > 255
        or file_name in {".", ".."}
        or any(character in file_name for character in ("/", "\\", "\x00", ":"))
        or file_name.endswith((" ", "."))
        or file_name.split(".", maxsplit=1)[0].upper() in _WINDOWS_RESERVED_NAMES
    ):
        raise ManifestError("file_name must be a safe base filename")
    return file_name


def _is_sha256_digest(value: object) -> bool:
    return isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None


def validate_manifest(manifest: object) -> FileManifest:
    """Validate and return a v1 manifest dictionary."""
    if not isinstance(manifest, dict):
        raise ManifestError("manifest must be a JSON object")
    if set(manifest) != _MANIFEST_FIELDS:
        missing = _MANIFEST_FIELDS - set(manifest)
        extra = set(manifest) - _MANIFEST_FIELDS
        raise ManifestError(f"invalid manifest fields (missing={missing}, extra={extra})")

    version = manifest["manifest_version"]
    file_name = _validate_file_name(manifest["file_name"])
    file_size = manifest["file_size"]
    chunk_size = manifest["chunk_size"]
    chunk_count = manifest["chunk_count"]
    file_sha256 = manifest["file_sha256"]
    raw_chunks = manifest["chunks"]

    if not isinstance(version, int) or isinstance(version, bool) or version != MANIFEST_VERSION:
        raise ManifestError(f"manifest_version must equal {MANIFEST_VERSION}")
    if not isinstance(file_size, int) or isinstance(file_size, bool) or file_size < 1:
        raise ManifestError("file_size must be a positive integer; empty files are unsupported")
    if (
        not isinstance(chunk_size, int)
        or isinstance(chunk_size, bool)
        or not 1 <= chunk_size <= MAX_CHUNK_SIZE
    ):
        raise ManifestError(f"chunk_size must be an integer in 1..{MAX_CHUNK_SIZE}")
    if not isinstance(chunk_count, int) or isinstance(chunk_count, bool):
        raise ManifestError("chunk_count must be an integer")
    if not _is_sha256_digest(file_sha256):
        raise ManifestError("file_sha256 must be 64 lowercase hexadecimal characters")
    if not isinstance(raw_chunks, list):
        raise ManifestError("chunks must be an array")

    expected_count = (file_size + chunk_size - 1) // chunk_size
    if expected_count > MAX_CHUNK_COUNT:
        raise ManifestError(f"chunk count exceeds maximum {MAX_CHUNK_COUNT}")
    if chunk_count != expected_count:
        raise ManifestError(f"chunk_count must equal {expected_count}")
    if len(raw_chunks) != expected_count:
        raise ManifestError(f"chunks must contain exactly {expected_count} entries")

    chunks: list[ChunkDescriptor] = []
    for index, raw_chunk in enumerate(raw_chunks):
        if not isinstance(raw_chunk, dict) or set(raw_chunk) != _CHUNK_FIELDS:
            raise ManifestError(f"chunk {index} must contain exactly index, length, and sha256")

        chunk_index = raw_chunk["index"]
        length = raw_chunk["length"]
        digest = raw_chunk["sha256"]
        expected_length = min(chunk_size, file_size - index * chunk_size)
        if not isinstance(chunk_index, int) or isinstance(chunk_index, bool):
            raise ManifestError(f"chunk {index} index must be an integer")
        if chunk_index != index:
            raise ManifestError(f"chunk indices must be in order; expected {index}")
        if not isinstance(length, int) or isinstance(length, bool) or length != expected_length:
            raise ManifestError(f"chunk {index} length must equal {expected_length}")
        if not _is_sha256_digest(digest):
            raise ManifestError(f"chunk {index} sha256 must be 64 lowercase hexadecimal characters")
        chunks.append({"index": chunk_index, "length": length, "sha256": digest})

    validated: FileManifest = {
        "manifest_version": version,
        "file_name": file_name,
        "file_size": file_size,
        "chunk_size": chunk_size,
        "chunk_count": chunk_count,
        "file_sha256": file_sha256,
        "chunks": chunks,
    }
    if len(_canonical_json(validated)) > MAX_MANIFEST_SIZE:
        raise ManifestError(f"manifest exceeds maximum size of {MAX_MANIFEST_SIZE} bytes")
    return validated


def _canonical_json(manifest: FileManifest) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_swarm_id(manifest: object) -> str:
    """Return the SHA-256 of the validated manifest's canonical JSON bytes."""
    validated = validate_manifest(manifest)
    return hashlib.sha256(_canonical_json(validated)).hexdigest()


def build_manifest(
    file_path: Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> FileManifest:
    """Build a manifest by hashing a file in bounded-size chunks."""
    if (
        not isinstance(chunk_size, int)
        or isinstance(chunk_size, bool)
        or not 1 <= chunk_size <= MAX_CHUNK_SIZE
    ):
        raise ManifestError(f"chunk_size must be an integer in 1..{MAX_CHUNK_SIZE}")

    file_name = _validate_file_name(file_path.name)
    chunks: list[ChunkDescriptor] = []
    file_hash = hashlib.sha256()
    file_size = 0

    with file_path.open("rb") as source:
        while data := source.read(chunk_size):
            file_hash.update(data)
            file_size += len(data)
            chunks.append(
                {
                    "index": len(chunks),
                    "length": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
            if len(chunks) > MAX_CHUNK_COUNT:
                raise ManifestError(f"chunk count exceeds maximum {MAX_CHUNK_COUNT}")

    if file_size == 0:
        raise ManifestError("empty files are unsupported")

    manifest: FileManifest = {
        "manifest_version": MANIFEST_VERSION,
        "file_name": file_name,
        "file_size": file_size,
        "chunk_size": chunk_size,
        "chunk_count": len(chunks),
        "file_sha256": file_hash.hexdigest(),
        "chunks": chunks,
    }
    return validate_manifest(manifest)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_manifest(manifest_path: Path) -> FileManifest:
    """Read and validate a JSON manifest without loading oversized input."""
    with manifest_path.open("rb") as source:
        raw = source.read(MAX_MANIFEST_SIZE + 1)
    if len(raw) > MAX_MANIFEST_SIZE:
        raise ManifestError(f"manifest exceeds maximum size of {MAX_MANIFEST_SIZE} bytes")
    try:
        parsed = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
        raise ManifestError(f"invalid manifest JSON: {error}") from error
    return validate_manifest(parsed)


def write_manifest(manifest: object, manifest_path: Path) -> None:
    """Validate and atomically write a manifest as UTF-8 JSON."""
    validated = validate_manifest(manifest)
    payload = _canonical_json(validated)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=manifest_path.parent,
            prefix=f".{manifest_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, manifest_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
