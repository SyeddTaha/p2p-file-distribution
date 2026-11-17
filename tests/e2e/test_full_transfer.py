"""Tracker-driven multi-peer file transfer over loopback TCP."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from collections.abc import Awaitable, Callable, MutableMapping
from pathlib import Path
from typing import Any

import httpx
import pytest

from p2p.peer.client import SwarmPeer
from p2p.storage.manifest import build_manifest
from p2p.tracker.registry import SwarmRegistry
from p2p.tracker.server import app, get_registry


class RecordingTrackerApp:
    """Capture lifecycle events while forwarding requests to the real FastAPI app."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[MutableMapping[str, Any]]],
        send: Callable[[MutableMapping[str, Any]], Awaitable[None]],
    ) -> None:
        body = bytearray()

        async def record_receive() -> MutableMapping[str, Any]:
            message = await receive()
            if message["type"] == "http.request":
                body.extend(message.get("body", b""))
            return message

        await app(scope, record_receive, send)
        if scope["type"] == "http" and scope["path"] == "/announce" and body:
            event_data = json.loads(body)
            self.events.append((event_data["peer_id"], event_data["event"]))


@pytest.mark.asyncio
async def test_tracker_seed_and_three_concurrent_leechers(
    tmp_path: Path,
) -> None:
    contents = random.Random(20261109).randbytes(16 * 1024)
    source = tmp_path / "payload.bin"
    source.write_bytes(contents)
    manifest = build_manifest(source, chunk_size=512)
    registry = SwarmRegistry()
    recording_app = RecordingTrackerApp()
    previous_override = app.dependency_overrides.get(get_registry)
    app.dependency_overrides[get_registry] = lambda: registry
    transport = httpx.ASGITransport(app=recording_app)
    seeder = SwarmPeer(
        manifest,
        "http://tracker.test",
        tmp_path,
        seed_file=source,
        tracker_transport=transport,
        peer_id="e2e-seeder",
    )
    leechers = [
        SwarmPeer(
            manifest,
            "http://tracker.test",
            tmp_path / f"downloads-{index}",
            tracker_transport=transport,
            peer_id=f"e2e-leecher-{index}",
        )
        for index in range(3)
    ]
    heartbeat_tasks: list[asyncio.Task[None]] = []

    try:
        async with asyncio.timeout(30):
            await seeder.start()
            await seeder.heartbeat()
            await asyncio.gather(*(peer.start() for peer in leechers))
            heartbeat_tasks = [
                peer._heartbeat_task for peer in [seeder, *leechers] if peer._heartbeat_task
            ]
            async with asyncio.TaskGroup() as task_group:
                tasks = [task_group.create_task(peer.download()) for peer in leechers]

            assert all(task.result().read_bytes() == contents for task in tasks)
            assert all(
                hashlib.sha256(task.result().read_bytes()).hexdigest() == manifest["file_sha256"]
                for task in tasks
            )
            assert all(peer.is_seeder for peer in leechers)
            assert all(peer.sent_haves for peer in leechers)
            assert any(peer.received_haves for peer in leechers)
            for peer in [seeder, *leechers]:
                record = registry.get_peer(seeder.swarm_id, peer.peer_id)
                assert record is not None and record.is_seeder
    finally:
        await asyncio.wait_for(
            asyncio.gather(*(peer.close() for peer in [*leechers, seeder])),
            timeout=5,
        )
        if previous_override is None:
            app.dependency_overrides.pop(get_registry, None)
        else:
            app.dependency_overrides[get_registry] = previous_override

    assert all(task.done() for task in heartbeat_tasks)
    for peer in [seeder, *leechers]:
        peer_events = [event for peer_id, event in recording_app.events if peer_id == peer.peer_id]
        assert "started" in peer_events
        assert "heartbeat" in peer_events
        if peer is not seeder:
            assert "completed" in peer_events
        assert peer_events[-1] == "stopped"

    assert all(
        registry.get_peer(seeder.swarm_id, peer.peer_id) is None for peer in [seeder, *leechers]
    )


@pytest.mark.asyncio
async def test_completed_leecher_serves_verified_piece_to_later_leecher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contents = random.Random(20261117).randbytes(4097)
    source = tmp_path / "payload.bin"
    source.write_bytes(contents)
    manifest = build_manifest(source, chunk_size=512)
    registry = SwarmRegistry()
    recording_app = RecordingTrackerApp()
    previous_override = app.dependency_overrides.get(get_registry)
    app.dependency_overrides[get_registry] = lambda: registry
    transport = httpx.ASGITransport(app=recording_app)
    seeder = SwarmPeer(
        manifest,
        "http://tracker.test",
        tmp_path,
        seed_file=source,
        tracker_transport=transport,
        peer_id="relay-seeder",
    )
    first_leecher = SwarmPeer(
        manifest,
        "http://tracker.test",
        tmp_path / "first-download",
        tracker_transport=transport,
        peer_id="relay-first",
    )
    second_leecher = SwarmPeer(
        manifest,
        "http://tracker.test",
        tmp_path / "second-download",
        tracker_transport=transport,
        peer_id="relay-second",
    )
    served_pieces: list[tuple[int, int]] = []

    try:
        async with asyncio.timeout(30):
            await seeder.start()
            await first_leecher.start()
            first_path = await first_leecher.download()
            assert first_path.read_bytes() == contents
            assert first_leecher.is_seeder
            assert first_leecher.storage is not None
            assert len(first_leecher.storage.verified_chunks) == manifest["chunk_count"]

            original_read_chunk = first_leecher._read_chunk

            async def record_served_piece(index: int) -> bytes:
                data = await original_read_chunk(index)
                served_pieces.append((index, len(data)))
                return data

            monkeypatch.setattr(first_leecher, "_read_chunk", record_served_piece)

            # Remove the origin from the tracker before the second download. The
            # completed leecher is then the only possible source of PIECE payloads.
            await seeder.close()
            assert registry.get_peer(first_leecher.swarm_id, seeder.peer_id) is None

            await second_leecher.start()
            second_path = await second_leecher.download()

            assert served_pieces
            assert sum(length for _, length in served_pieces) == len(contents)
            assert second_path.read_bytes() == contents
            assert hashlib.sha256(second_path.read_bytes()).hexdigest() == manifest["file_sha256"]
            assert second_leecher.is_seeder
    finally:
        await asyncio.wait_for(
            asyncio.gather(seeder.close(), first_leecher.close(), second_leecher.close()),
            timeout=5,
        )
        if previous_override is None:
            app.dependency_overrides.pop(get_registry, None)
        else:
            app.dependency_overrides[get_registry] = previous_override
