"""Verified chunk persistence and atomic file finalization."""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

from p2p.storage.manifest import FileManifest, _validate_file_name, validate_manifest


class ChunkIntegrityError(ValueError):
    """Raised when chunk data does not match its validated manifest entry."""


class IncompleteFileError(ValueError):
    """Raised when finalization is attempted before all chunks are verified."""


class FileIntegrityError(ValueError):
    """Raised when the reconstructed file does not match its manifest digest."""


def validate_safe_filename(download_dir: Path, file_name: str) -> Path:
    """Resolve a safe base filename beneath the requested download directory."""
    safe_name = _validate_file_name(file_name)
    base_dir = download_dir.resolve()
    candidate = base_dir / safe_name
    target_path = candidate.resolve()
    if target_path != candidate:
        raise ValueError("destination filename must not be a symbolic link")
    if target_path.parent != base_dir:
        raise ValueError("path escapes download directory")
    return target_path


class StorageManager:
    """Own a single download's temporary file and verified chunk state."""

    def __init__(self, manifest: object, download_dir: Path) -> None:
        self.manifest: FileManifest = validate_manifest(manifest)
        download_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir = download_dir.resolve()
        self.target_path = validate_safe_filename(self.download_dir, self.manifest["file_name"])
        self.part_path = self.target_path.with_name(f"{self.target_path.name}.part")
        self._verified_chunks: set[int] = set()
        self._finalized = False

        resolved_part_path = self.part_path.resolve()
        if resolved_part_path.parent != self.download_dir or resolved_part_path != self.part_path:
            raise ValueError("temporary file path must be a regular child of download directory")
        with self.part_path.open("wb"):
            pass

    @property
    def verified_chunks(self) -> frozenset[int]:
        """Return an immutable snapshot of verified chunk indices."""
        return frozenset(self._verified_chunks)

    def write_chunk(self, index: int, data: bytes) -> bool:
        """Verify and persist one chunk; return False for an already verified index."""
        if self._finalized:
            raise RuntimeError("cannot write chunks after finalization")
        if not isinstance(index, int) or isinstance(index, bool):
            raise ChunkIntegrityError("chunk index must be an integer")
        if not 0 <= index < self.manifest["chunk_count"]:
            raise ChunkIntegrityError("chunk index is outside the manifest range")
        if index in self._verified_chunks:
            return False
        if not isinstance(data, bytes):
            raise ChunkIntegrityError("chunk data must be bytes")

        descriptor = self.manifest["chunks"][index]
        if len(data) != descriptor["length"]:
            raise ChunkIntegrityError(
                f"chunk {index} length {len(data)} does not match {descriptor['length']}"
            )
        digest = hashlib.sha256(data).hexdigest()
        if not hmac.compare_digest(digest, descriptor["sha256"]):
            raise ChunkIntegrityError(f"chunk {index} SHA-256 does not match manifest")

        offset = index * self.manifest["chunk_size"]
        with self.part_path.open("r+b") as part_file:
            part_file.seek(offset)
            written = part_file.write(data)
            if written != len(data):
                raise OSError(
                    f"short write for chunk {index}: wrote {written} of {len(data)} bytes"
                )
            part_file.flush()
        self._verified_chunks.add(index)
        return True

    def finalize(self) -> Path:
        """Verify the complete temporary file and atomically publish it."""
        if self._finalized:
            raise RuntimeError("file has already been finalized")
        expected_chunks = set(range(self.manifest["chunk_count"]))
        if self._verified_chunks != expected_chunks:
            raise IncompleteFileError("cannot finalize before every chunk is verified")

        with self.part_path.open("r+b") as part_file:
            part_file.flush()
            os.fsync(part_file.fileno())

        file_hash = hashlib.sha256()
        with self.part_path.open("rb") as part_file:
            while data := part_file.read(1024 * 1024):
                file_hash.update(data)
        if not hmac.compare_digest(file_hash.hexdigest(), self.manifest["file_sha256"]):
            raise FileIntegrityError("complete file SHA-256 does not match manifest")

        os.replace(self.part_path, self.target_path)
        self._finalized = True
        return self.target_path
