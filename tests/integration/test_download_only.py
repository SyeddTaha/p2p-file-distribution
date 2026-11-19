"""Download-only peers never offer verified chunks over loopback TCP."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from p2p.peer.client import SwarmPeer
from p2p.peer.connection import PeerConnection
from p2p.protocol import Bitfield, ConnectionClosed
from p2p.storage.manifest import build_manifest
from p2p.tracker.registry import SwarmRegistry
from p2p.tracker.server import app, get_registry


@pytest.mark.parametrize("complete", [False, True], ids=["partial", "complete"])
async def test_download_only_peer_rejects_requests_for_verified_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    complete: bool,
) -> None:
    source = tmp_path / "payload.bin"
    source.write_bytes(b"abcdefgh")
    manifest = build_manifest(source, chunk_size=4)
    registry = SwarmRegistry()
    monkeypatch.setitem(app.dependency_overrides, get_registry, lambda: registry)
    peer = SwarmPeer(
        manifest,
        "http://tracker.test",
        tmp_path / "downloads",
        upload_enabled=False,
        tracker_transport=httpx.ASGITransport(app=app),
        peer_id="download-only",
    )
    observer: PeerConnection | None = None
    later_observer: PeerConnection | None = None
    server = None
    heartbeat = None
    try:
        async with asyncio.timeout(5):
            await peer.start()
            server = peer._server
            heartbeat = peer._heartbeat_task

            async def connect_observer(peer_id: str) -> PeerConnection:
                return await PeerConnection.connect(
                    "127.0.0.1",
                    peer.listen_port,
                    swarm_id=peer.swarm_id,
                    my_peer_id=peer_id,
                    my_listen_port=1,
                    chunk_count=manifest["chunk_count"],
                    local_bitfield=Bitfield.from_indices([], manifest["chunk_count"]),
                )

            observer = await connect_observer("existing-observer")
            assert peer.storage is not None
            peer.storage.write_chunk(0, b"abcd")
            await peer._on_chunk_verified(0)
            if complete:
                peer.storage.write_chunk(1, b"efgh")
                await peer._on_chunk_verified(1)
                peer.storage.finalize()
            assert peer.is_seeder is complete
            assert not peer.sent_haves

            # A connection made after chunk acceptance/finalization still gets
            # an empty BITFIELD. An older connection must not receive HAVE.
            later_observer = await connect_observer("later-observer")
            assert later_observer.remote_bitfield is not None
            assert not later_observer.remote_bitfield.to_indices(manifest["chunk_count"])
            for connection in (observer, later_observer):
                await connection.send_request(0)
                with pytest.raises(ConnectionClosed):
                    await connection.receive_message()
    finally:
        async with asyncio.timeout(5):
            await asyncio.gather(
                *(
                    connection.close()
                    for connection in (observer, later_observer)
                    if connection is not None
                )
            )
            await peer.close()
    assert server is not None
    assert server.active_connection_count == 0
    assert not server._connection_tasks
    assert heartbeat is not None and heartbeat.done()
    assert registry.get_peer(peer.swarm_id, peer.peer_id) is None
