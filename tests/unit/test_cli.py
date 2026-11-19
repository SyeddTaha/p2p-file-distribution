"""Tests for the p2p command-line interface."""

from __future__ import annotations

import io
import json
import tomllib
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any, Self

import pytest

from p2p.cli import build_parser, main
from p2p.peer.downloader import NoAvailablePeersError
from p2p.storage.manifest import build_manifest, load_manifest, write_manifest


def test_cli_parser_exposes_all_milestone_commands() -> None:
    parser = build_parser()
    parsed = [
        parser.parse_args(["tracker-start"]),
        parser.parse_args(["create-manifest", "input.bin"]),
        parser.parse_args(
            ["seed-file", "manifest.json", "input.bin", "--tracker-url", "http://localhost"]
        ),
        parser.parse_args(
            [
                "download-file",
                "manifest.json",
                "--download-dir",
                "downloads",
                "--tracker-url",
                "http://localhost",
            ]
        ),
    ]
    assert [args.command for args in parsed] == [
        "tracker-start",
        "create-manifest",
        "seed-file",
        "download-file",
    ]


def test_create_manifest_command_writes_manifest(tmp_path: Path) -> None:
    source = tmp_path / "sample.bin"
    source.write_bytes(b"abcdefgh")
    output = tmp_path / "subdirectory" / "sample.json"

    main(["create-manifest", str(source), "--chunk-size", "4", "--output", str(output)])

    manifest = load_manifest(output)
    assert manifest["file_name"] == source.name
    assert manifest["chunk_count"] == 2
    assert json.loads(output.read_text(encoding="utf-8"))["file_size"] == 8


def test_tracker_start_runs_uvicorn_with_requested_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, Any] = {}

    def fake_run(app: str, *, host: str, port: int) -> None:
        called.update(app=app, host=host, port=port)

    monkeypatch.setattr("p2p.cli.uvicorn.run", fake_run)
    main(["tracker-start", "--host", "127.0.0.1", "--port", "8765"])

    assert called == {
        "app": "p2p.tracker.server:app",
        "host": "127.0.0.1",
        "port": 8765,
    }


def test_cli_reports_missing_file_without_traceback(tmp_path: Path) -> None:
    stderr = io.StringIO()
    missing_file = tmp_path / "missing.bin"
    with redirect_stderr(stderr), pytest.raises(SystemExit) as exc_info:
        main(["create-manifest", str(missing_file)])

    assert exc_info.value.code == 1
    assert missing_file.name in stderr.getvalue()
    assert "Traceback" not in stderr.getvalue()


def test_cli_reports_invalid_tracker_url_without_traceback(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abcdefgh")
    manifest_path = tmp_path / "manifest.json"
    write_manifest(build_manifest(source, chunk_size=4), manifest_path)
    stderr = io.StringIO()

    with redirect_stderr(stderr), pytest.raises(SystemExit) as exc_info:
        main(
            [
                "seed-file",
                str(manifest_path),
                str(source),
                "--tracker-url",
                "ftp://tracker.test",
            ]
        )

    assert exc_info.value.code == 1
    assert "tracker_url must use http:// or https://" in stderr.getvalue()
    assert "Traceback" not in stderr.getvalue()


def test_cli_reports_no_available_peers_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abcdefgh")
    manifest_path = tmp_path / "manifest.json"
    write_manifest(build_manifest(source, chunk_size=4), manifest_path)
    stderr = io.StringIO()

    class NoPeer:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def download(self) -> Path:
            raise NoAvailablePeersError("tracker returned no reachable peers")

    monkeypatch.setattr("p2p.cli.SwarmPeer", lambda *_args, **_kwargs: NoPeer())
    with (
        redirect_stderr(stderr),
        pytest.raises(SystemExit) as exc_info,
    ):
        main(
            [
                "download-file",
                str(manifest_path),
                "--download-dir",
                str(tmp_path / "downloads"),
                "--tracker-url",
                "http://tracker.test",
            ]
        )

    assert exc_info.value.code == 1
    assert "tracker returned no reachable peers" in stderr.getvalue()
    assert "Traceback" not in stderr.getvalue()


def test_pyproject_registers_console_entry_point() -> None:
    with Path("pyproject.toml").open("rb") as project_file:
        config = tomllib.load(project_file)
    assert config["project"]["scripts"]["p2p"] == "p2p.cli:main"


@pytest.mark.parametrize(
    ("command", "no_upload"),
    [("seed-file", False), ("download-file", False), ("download-file", True)],
)
def test_peer_cli_commands_run_and_keep_peer_serving(
    command: str,
    no_upload: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abcdefgh")
    manifest_path = tmp_path / "manifest.json"
    write_manifest(build_manifest(source, chunk_size=4), manifest_path)
    calls: dict[str, Any] = {"waited": False, "downloaded": False}

    class StubPeer:
        swarm_id = "a" * 64
        host = "127.0.0.1"
        listen_port = 32123

        def __init__(self, *_args: Any, **kwargs: Any) -> None:
            calls["kwargs"] = kwargs

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def download(self) -> Path:
            calls["downloaded"] = True
            return source

        async def wait_until_stopped(self) -> None:
            calls["waited"] = True

    monkeypatch.setattr("p2p.cli.SwarmPeer", StubPeer)
    if command == "seed-file":
        args = [
            command,
            str(manifest_path),
            str(source),
            "--tracker-url",
            "http://tracker.test",
        ]
    else:
        args = [
            command,
            str(manifest_path),
            "--download-dir",
            str(tmp_path / "downloads"),
            "--tracker-url",
            "http://tracker.test",
        ]

    if no_upload:
        args.append("--no-upload")
    main(args)

    assert calls["waited"] is True
    assert calls["downloaded"] is (command == "download-file")
    if command == "download-file":
        assert calls["kwargs"]["upload_enabled"] is not no_upload


@pytest.mark.parametrize("command", ["seed-file", "download-file"])
def test_peer_cli_commands_pass_upload_rate_limit(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abcdefgh")
    manifest_path = tmp_path / "manifest.json"
    write_manifest(build_manifest(source, chunk_size=4), manifest_path)
    calls: dict[str, Any] = {}

    class StubPeer:
        swarm_id = "a" * 64
        host = "127.0.0.1"
        listen_port = 32123

        def __init__(self, *_args: Any, **kwargs: Any) -> None:
            calls["kwargs"] = kwargs

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def download(self) -> Path:
            return source

        async def wait_until_stopped(self) -> None:
            pass

    monkeypatch.setattr("p2p.cli.SwarmPeer", StubPeer)
    if command == "seed-file":
        args = [
            command,
            str(manifest_path),
            str(source),
            "--tracker-url",
            "http://tracker.test",
            "--upload-rate-limit",
            "1048576",
        ]
    else:
        args = [
            command,
            str(manifest_path),
            "--download-dir",
            str(tmp_path / "downloads"),
            "--tracker-url",
            "http://tracker.test",
            "--upload-rate-limit",
            "524288",
        ]

    main(args)
    expected_limit = 1048576.0 if command == "seed-file" else 524288.0
    assert calls["kwargs"]["upload_rate_limit"] == expected_limit
