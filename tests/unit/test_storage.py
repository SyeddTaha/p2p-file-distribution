"""Unit tests for manifest construction and verified file storage."""

import hashlib
import json
from pathlib import Path

import pytest

from p2p.config import DEFAULT_CHUNK_SIZE, MAX_CHUNK_SIZE
from p2p.storage.manager import (
    ChunkIntegrityError,
    FileIntegrityError,
    IncompleteFileError,
    StorageManager,
    validate_safe_filename,
)
from p2p.storage.manifest import (
    ManifestError,
    build_manifest,
    compute_swarm_id,
    load_manifest,
    validate_manifest,
    write_manifest,
)


def _manifest_for(data: bytes, file_name: str = "sample.bin", chunk_size: int = 4) -> dict:
    chunks = [
        {
            "index": index,
            "length": len(data[offset : offset + chunk_size]),
            "sha256": hashlib.sha256(data[offset : offset + chunk_size]).hexdigest(),
        }
        for index, offset in enumerate(range(0, len(data), chunk_size))
    ]
    return {
        "manifest_version": 1,
        "file_name": file_name,
        "file_size": len(data),
        "chunk_size": chunk_size,
        "chunk_count": len(chunks),
        "file_sha256": hashlib.sha256(data).hexdigest(),
        "chunks": chunks,
    }


def test_build_manifest_and_swarm_id_are_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "input.bin"
    source.write_bytes(b"abcdefghij")

    manifest = build_manifest(source, chunk_size=4)

    assert manifest == _manifest_for(b"abcdefghij", "input.bin", 4)
    swarm_id = compute_swarm_id(manifest)
    expected_id = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert swarm_id == compute_swarm_id(dict(reversed(list(manifest.items()))))
    assert swarm_id == expected_id
    assert len(swarm_id) == 64


@pytest.mark.parametrize(
    "data",
    [b"x", b"abcd", b"abcdefgh", b"abcdefghi"],
    ids=["one-byte", "one-full-chunk", "exact-multiple", "multiple-with-remainder"],
)
def test_manifest_and_storage_handle_chunk_edge_sizes(tmp_path: Path, data: bytes) -> None:
    source = tmp_path / "edge.bin"
    source.write_bytes(data)
    manifest = build_manifest(source, chunk_size=4)
    storage = StorageManager(manifest, tmp_path / "download")

    for chunk in manifest["chunks"]:
        start = chunk["index"] * manifest["chunk_size"]
        storage.write_chunk(chunk["index"], data[start : start + chunk["length"]])

    assert storage.finalize().read_bytes() == data


def test_build_manifest_rejects_empty_file(tmp_path: Path) -> None:
    source = tmp_path / "empty.bin"
    source.write_bytes(b"")

    with pytest.raises(ManifestError, match="empty"):
        build_manifest(source)


def test_validate_manifest_accepts_valid_manifest() -> None:
    manifest = _manifest_for(b"abcdefghij")

    assert validate_manifest(manifest) == manifest


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manifest_version", True),
        ("file_name", "../escape.bin"),
        ("file_size", True),
        ("chunk_size", MAX_CHUNK_SIZE + 1),
        ("chunk_count", 1),
        ("file_sha256", "g" * 64),
        ("chunks", []),
    ],
)
def test_validate_manifest_rejects_invalid_fields(field: str, value: object) -> None:
    manifest = _manifest_for(b"abcdefgh")
    manifest[field] = value

    with pytest.raises(ManifestError):
        validate_manifest(manifest)


def test_validate_manifest_rejects_wrong_chunk_descriptor() -> None:
    manifest = _manifest_for(b"abcdefgh")
    manifest["chunks"][1]["length"] = 3

    with pytest.raises(ManifestError, match="length"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_boolean_chunk_index() -> None:
    manifest = _manifest_for(b"abcdefgh")
    manifest["chunks"][0]["index"] = True

    with pytest.raises(ManifestError, match="index"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_chunk_count_above_limit_before_chunk_iteration() -> None:
    manifest = _manifest_for(b"data")
    manifest["file_size"] = 30_001 * manifest["chunk_size"]
    manifest["chunk_count"] = 30_001
    manifest["chunks"] = []

    with pytest.raises(ManifestError, match="chunk count exceeds maximum"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_uppercase_digest() -> None:
    manifest = _manifest_for(b"abcdefgh")
    manifest["chunks"][0]["sha256"] = manifest["chunks"][0]["sha256"].upper()

    with pytest.raises(ManifestError, match="lowercase"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_invalid_file_digest() -> None:
    manifest = _manifest_for(b"abcdefgh")
    manifest["file_sha256"] = "A" * 64

    with pytest.raises(ManifestError, match="file_sha256"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_unknown_fields() -> None:
    manifest = _manifest_for(b"data")
    manifest["unexpected"] = "value"

    with pytest.raises(ManifestError, match="extra"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_empty_file_and_out_of_range_chunk_size() -> None:
    with pytest.raises(ManifestError, match="empty"):
        validate_manifest(_manifest_for(b""))

    invalid_size = _manifest_for(b"a")
    invalid_size["chunk_size"] = 0
    with pytest.raises(ManifestError, match="chunk_size"):
        validate_manifest(invalid_size)


@pytest.mark.parametrize(
    "file_name",
    [
        "",
        ".",
        "..",
        "../escape",
        "subdir/file",
        r"subdir\file",
        "/absolute",
        "C:drive-relative.bin",
        r"C:\file",
        "nul\x00.bin",
        "x" * 256,
    ],
)
def test_validate_safe_filename_rejects_unsafe_names(tmp_path: Path, file_name: str) -> None:
    with pytest.raises(ValueError):
        validate_safe_filename(tmp_path, file_name)


@pytest.mark.parametrize("file_name", ["CON", "nul.txt", "LPT1.log", "trailing.", "trailing "])
def test_validate_safe_filename_rejects_windows_reserved_names(
    tmp_path: Path,
    file_name: str,
) -> None:
    with pytest.raises(ValueError):
        validate_safe_filename(tmp_path, file_name)


def test_validate_safe_filename_returns_child_of_download_directory(tmp_path: Path) -> None:
    target = validate_safe_filename(tmp_path, "received.bin")

    assert target == tmp_path.resolve() / "received.bin"
    assert target.parent == tmp_path.resolve()


def test_validate_safe_filename_rejects_symbolic_link(tmp_path: Path) -> None:
    linked_file = tmp_path / "linked.bin"
    linked_file.symlink_to(tmp_path / "real.bin")

    with pytest.raises(ValueError, match="symbolic link"):
        validate_safe_filename(tmp_path, "linked.bin")


def test_load_manifest_checks_size_before_parsing(tmp_path: Path) -> None:
    manifest_path = tmp_path / "oversized.json"
    manifest_path.write_bytes(b" " * (4 * 1024 * 1024 + 1))

    with pytest.raises(ManifestError, match="maximum size"):
        load_manifest(manifest_path)


@pytest.mark.parametrize("contents", [b"{broken", b'{"manifest_version":1,"manifest_version":1}'])
def test_load_manifest_rejects_malformed_json_and_duplicate_keys(
    tmp_path: Path,
    contents: bytes,
) -> None:
    manifest_path = tmp_path / "invalid.json"
    manifest_path.write_bytes(contents)

    with pytest.raises(ManifestError):
        load_manifest(manifest_path)


def test_storage_rejects_corrupt_chunk_without_writing_it(tmp_path: Path) -> None:
    manifest = _manifest_for(b"abcdefgh")
    storage = StorageManager(manifest, tmp_path)

    with pytest.raises(ChunkIntegrityError, match="SHA-256"):
        storage.write_chunk(0, b"xxxx")

    assert storage.part_path.read_bytes() == b""
    assert storage.verified_chunks == frozenset()


def test_storage_rejects_wrong_length_and_index(tmp_path: Path) -> None:
    storage = StorageManager(_manifest_for(b"abcdefgh"), tmp_path)

    with pytest.raises(ChunkIntegrityError, match="length"):
        storage.write_chunk(0, b"abc")
    with pytest.raises(ChunkIntegrityError, match="index"):
        storage.write_chunk(2, b"ijkl")


def test_storage_accepts_verified_chunks_and_ignores_duplicate(tmp_path: Path) -> None:
    storage = StorageManager(_manifest_for(b"abcdefgh"), tmp_path)

    assert storage.write_chunk(0, b"abcd") is True
    assert storage.write_chunk(0, b"xxxx") is False
    assert storage.part_path.read_bytes() == b"abcd"
    assert storage.verified_chunks == frozenset({0})


def test_finalize_rejects_incomplete_file(tmp_path: Path) -> None:
    storage = StorageManager(_manifest_for(b"abcdefgh"), tmp_path)
    storage.write_chunk(0, b"abcd")

    with pytest.raises(IncompleteFileError):
        storage.finalize()

    assert not storage.target_path.exists()
    assert storage.part_path.exists()


def test_finalize_verifies_and_atomically_publishes_complete_file(tmp_path: Path) -> None:
    data = b"abcdefgh"
    storage = StorageManager(_manifest_for(data), tmp_path)
    storage.write_chunk(1, b"efgh")
    storage.write_chunk(0, b"abcd")

    final_path = storage.finalize()

    assert final_path == tmp_path.resolve() / "sample.bin"
    assert final_path.read_bytes() == data
    assert not storage.part_path.exists()
    assert hashlib.sha256(final_path.read_bytes()).hexdigest() == _manifest_for(data)["file_sha256"]


def test_finalize_keeps_part_file_when_whole_file_hash_fails(tmp_path: Path) -> None:
    manifest = _manifest_for(b"abcdefgh")
    manifest["file_sha256"] = "0" * 64
    storage = StorageManager(manifest, tmp_path)
    storage.write_chunk(0, b"abcd")
    storage.write_chunk(1, b"efgh")

    with pytest.raises(FileIntegrityError, match="complete file SHA-256"):
        storage.finalize()

    assert storage.part_path.read_bytes() == b"abcdefgh"
    assert not storage.target_path.exists()


def test_load_manifest_round_trips_json(tmp_path: Path) -> None:
    manifest = _manifest_for(b"manifest bytes")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert load_manifest(manifest_path) == manifest


def test_write_manifest_atomically_round_trips_json(tmp_path: Path) -> None:
    manifest = _manifest_for(b"manifest bytes")
    manifest_path = tmp_path / "manifests" / "file.json"

    write_manifest(manifest, manifest_path)

    assert load_manifest(manifest_path) == manifest
    assert list(manifest_path.parent.glob("*.tmp")) == []
    assert list(manifest_path.parent.glob(".*.tmp")) == []


def test_write_manifest_rejects_invalid_input_without_replacing_existing_file(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("keep existing", encoding="utf-8")
    invalid_manifest = _manifest_for(b"payload")
    invalid_manifest["chunk_count"] = 9

    with pytest.raises(ManifestError):
        write_manifest(invalid_manifest, manifest_path)

    assert manifest_path.read_text(encoding="utf-8") == "keep existing"


def test_build_manifest_uses_default_chunk_size(tmp_path: Path) -> None:
    source = tmp_path / "file.bin"
    source.write_bytes(b"payload")

    assert build_manifest(source)["chunk_size"] == DEFAULT_CHUNK_SIZE
