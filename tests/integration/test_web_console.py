"""Console API driving real loopback TCP peers; no external network or fixed ports."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from p2p.storage.manager import StorageManager
from p2p.tracker.registry import SwarmRegistry
from p2p.tracker.server import app as tracker_app
from p2p.tracker.server import get_registry
from p2p.web.app import create_app
from p2p.web.service import Console, Transfer


@pytest.fixture
async def console_client(
    tmp_path: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, Console, SwarmRegistry]]:
    registry = SwarmRegistry()
    tracker = FastAPI()
    tracker.include_router(tracker_app.router)
    tracker.dependency_overrides[get_registry] = lambda: registry
    web = create_app(
        tmp_path / "console",
        "http://127.0.0.1:1",
        tracker_transport=httpx.ASGITransport(app=tracker),
    )
    async with web.router.lifespan_context(web):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=web),
            base_url="http://127.0.0.1",
            headers={"X-P2P-UI": "1"},
        ) as client:
            yield client, web.state.console, registry
    assert registry.peer_count() == 0
    assert all(t.task is not None and t.task.done() for t in web.state.console.transfers.values())
    assert all(
        t.stop_task is not None and t.stop_task.done() for t in web.state.console.transfers.values()
    )


async def wait_state(console: Console, transfer_id: str, expected: str) -> Transfer:
    async with asyncio.timeout(15):
        while True:
            transfer = console.transfers[transfer_id]
            assert transfer.state != "failed", transfer.error
            if transfer.state == expected:
                return transfer
            await asyncio.sleep(0.005)


async def start_peer(client: httpx.AsyncClient, asset_id: str, kind: str, **options: Any) -> str:
    response = await client.post(
        "/api/transfers", json={"asset_id": asset_id, "kind": kind, **options}
    )
    assert response.status_code == 202, response.text
    return str(response.json()["id"])


async def test_seed_progress_rate_limit_integrity_and_leecher_relay(
    console_client: tuple[httpx.AsyncClient, Console, SwarmRegistry],
) -> None:
    client, console, registry = console_client
    contents = random.Random(17).randbytes(512 * 1024)
    async with asyncio.timeout(25):
        imported = await client.post("/api/assets?name=payload.bin", content=contents)
        assert imported.status_code == 201
        asset = imported.json()
        exported = await client.get(f"/api/assets/{asset['id']}/manifest")
        manifest = exported.json()
        assert manifest["file_sha256"] == hashlib.sha256(contents).hexdigest()
        source_id = await start_peer(client, asset["id"], "seed", upload_rate_limit=262144.0)
        source = await wait_state(console, source_id, "seeding")
        imported_manifest = await client.post(
            "/api/assets?name=copy.json&manifest_only=true", content=exported.content
        )
        assert imported_manifest.status_code == 201
        imported_id = imported_manifest.json()["id"]
        download_id = await start_peer(client, imported_id, "download")
        async with asyncio.timeout(10):
            while True:
                snapshot = (await client.get("/api/state")).json()
                progress = next(t for t in snapshot["transfers"] if t["id"] == download_id)
                metrics = progress["metrics"]
                if metrics and metrics["verified_chunks"] == 1:
                    assert metrics["verified_bytes"] == 262144
                    assert metrics["final_integrity"] == "pending"
                    assert metrics["bytes_downloaded"] == 262144
                    assert any(c["state"] == "steady_state" for c in metrics["connections"])
                    break
                await asyncio.sleep(0.005)
        first = await wait_state(console, download_id, "completed")
        assert source.peer is not None and first.peer is not None
        assert source.peer.snapshot().upload_rate_limit == 262144.0
        first_metrics = first.peer.snapshot()
        assert first_metrics.duration_seconds >= 0.8  # 512 KiB through a 256 KiB/s bucket.
        assert first_metrics.bytes_downloaded == len(contents)
        assert first_metrics.final_integrity == "verified"
        assert first_metrics.downloaded_from == {source.peer.peer_id: len(contents)}
        first_metrics.downloaded_from.clear()
        assert first.peer.snapshot().downloaded_from == {source.peer.peer_id: len(contents)}
        downloaded = await client.get(f"/api/transfers/{download_id}/file")
        assert downloaded.content == contents
        assert hashlib.sha256(downloaded.content).hexdigest() == asset["file_sha256"]

        # Remove the origin. A completed UI download now supplies actual TCP PIECE bytes.
        await client.post(f"/api/transfers/{source_id}/stop")
        second_id = await start_peer(client, imported_id, "download")
        second = await wait_state(console, second_id, "completed")
        assert second.peer is not None
        assert second.peer.snapshot().downloaded_from == {first.peer.peer_id: len(contents)}
        assert first.peer.snapshot().bytes_uploaded == len(contents)
        assert (await client.get(f"/api/transfers/{second_id}/file")).content == contents
        assert registry.peer_count() == 2
        memberships = (await client.get("/api/state")).json()["tracker"]["swarms"]
        assert len(memberships) == 1 and len(memberships[0]["peers"]) == 2
        # Concurrent repeated stop calls share one cleanup and leave no listener.
        await asyncio.gather(*(client.post(f"/api/transfers/{download_id}/stop") for _ in range(3)))
        assert first.peer.snapshot().online is False


async def test_download_only_clients_receive_only_origin_payload(
    console_client: tuple[httpx.AsyncClient, Console, SwarmRegistry],
) -> None:
    client, console, _ = console_client
    async with asyncio.timeout(20):
        contents = random.Random(18).randbytes(512 * 1024)
        asset = (await client.post("/api/assets?name=baseline.bin", content=contents)).json()
        source_id = await start_peer(client, asset["id"], "seed")
        source = await wait_state(console, source_id, "seeding")
        ids = [
            await start_peer(client, asset["id"], "download", download_only=True) for _ in range(3)
        ]
        clients = await asyncio.gather(*(wait_state(console, key, "completed") for key in ids))
        assert source.peer is not None
        for transfer in clients:
            assert transfer.peer is not None
            metrics = transfer.peer.snapshot()
            assert metrics.upload_enabled is False
            assert metrics.bytes_uploaded == 0
            assert metrics.final_integrity == "verified"
            assert metrics.downloaded_from == {source.peer.peer_id: len(contents)}
        assert source.peer.snapshot().bytes_uploaded == 3 * len(contents)


async def test_assets_validation_action_guard_and_static_files(
    console_client: tuple[httpx.AsyncClient, Console, SwarmRegistry],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, console, _ = console_client
    async with asyncio.timeout(15):
        page = await client.get("/")
        assert page.status_code == 200 and "Peer Network" in page.text
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
        for filename in ("app.js", "style.css"):
            assert (await client.get(f"/static/{filename}")).status_code == 200
        assert (await client.get("/", headers={"Host": "evil.example"})).status_code == 400
        assert (
            await client.get("/api/state", headers={"Origin": "https://evil.example"})
        ).status_code == 403
        client.headers.pop("X-P2P-UI")
        assert (await client.post("/api/assets?name=x", content=b"x")).status_code == 403
        client.headers["X-P2P-UI"] = "1"
        for name in ("../escape", "C:escape", "CON", "..", "test."):
            response = await client.post("/api/assets", params={"name": name}, content=b"data")
            assert response.status_code == 400, response.text
        assert not (tmp_path / "escape").exists()
        for raw in (b"{}", b'{"x":1,"x":2}', b"not json"):
            response = await client.post(
                "/api/assets?name=bad.json&manifest_only=true", content=raw
            )
            assert response.status_code == 400
        assert not console.assets
        response = await client.post("/api/transfers", content=b"x" * 8193)
        assert response.status_code == 413
        asset = (await client.post("/api/assets?name=manifest.json", content=b"bytes")).json()
        for options in ({"upload_rate_limit": -1}, {"download_only": "true"}, {"extra": 1}):
            response = await client.post(
                "/api/transfers", json={"asset_id": asset["id"], "kind": "download", **options}
            )
            assert response.status_code == 422
        assert (await client.get("/api/transfers/missing/file")).status_code == 404
        assert (await client.get("/api/assets/missing/manifest")).status_code == 404
        assert (await client.post("/api/transfers/missing/stop")).status_code == 404
        assert (await client.get(f"/api/assets/{asset['id']}/manifest")).json()[
            "file_name"
        ] == "manifest.json"
        monkeypatch.setattr("p2p.web.service.WEB_MAX_FILE_BYTES", 3)
        assert (await client.post("/api/assets?name=large", content=b"1234")).status_code == 413
        assert not list(console.workspace.rglob("large"))
        monkeypatch.setattr("p2p.web.service.WEB_MAX_ASSETS", 1)
        assert (await client.post("/api/assets?name=another", content=b"x")).status_code == 429


async def test_no_peers_failure_and_early_stop(
    console_client: tuple[httpx.AsyncClient, Console, SwarmRegistry],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, console, _ = console_client
    async with asyncio.timeout(15):
        asset = (await client.post("/api/assets?name=alone", content=b"abc")).json()
        transfer_id = await start_peer(client, asset["id"], "download")
        transfer = console.transfers[transfer_id]
        assert transfer.task is not None
        await transfer.task
        assert transfer.state == "failed" and "no reachable peers" in str(transfer.error)
        assert transfer.peer is not None and not transfer.peer.snapshot().online
        assert (await client.get(f"/api/transfers/{transfer_id}/file")).status_code == 409
        second_id = await start_peer(client, asset["id"], "download")
        await client.post(f"/api/transfers/{second_id}/stop")
        assert console.transfers[second_id].state == "stopped"
        monkeypatch.setattr("p2p.web.service.WEB_MAX_TRANSFERS", 2)
        assert (
            await client.post("/api/transfers", json={"asset_id": asset["id"], "kind": "seed"})
        ).status_code == 429


async def test_live_stop_cancels_incomplete_download_and_shutdown_cleans_membership(
    console_client: tuple[httpx.AsyncClient, Console, SwarmRegistry],
) -> None:
    client, console, registry = console_client
    async with asyncio.timeout(15):
        asset = (await client.post("/api/assets?name=cancel.bin", content=b"x" * 524288)).json()
        seed_id = await start_peer(client, asset["id"], "seed", upload_rate_limit=65536.0)
        await wait_state(console, seed_id, "seeding")
        key = await start_peer(client, asset["id"], "download")
        await wait_state(console, key, "downloading")
        await client.post(f"/api/transfers/{key}/stop")
        transfer = console.transfers[key]
        assert transfer.state == "stopped" and transfer.output is None
        assert transfer.peer is not None
        assert transfer.peer.snapshot().final_integrity == "pending"
        await console.close()
        assert registry.peer_count() == 0
        assert (
            await client.post("/api/transfers", json={"asset_id": asset["id"], "kind": "seed"})
        ).status_code == 503


async def test_offline_tracker_and_missing_benchmarks(tmp_path: Path) -> None:
    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("tracker unavailable", request=request)

    web = create_app(
        tmp_path,
        tracker_transport=httpx.MockTransport(offline),
        benchmark_csv=tmp_path / "missing.csv",
    )
    async with asyncio.timeout(10), web.router.lifespan_context(web):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=web), base_url="http://127.0.0.1"
        ) as client:
            snapshot = (await client.get("/api/state")).json()
            assert snapshot["tracker"]["online"] is False
            assert snapshot["tracker"]["swarms"] is None
            assert "unavailable" in snapshot["tracker"]["error"]
            result = (await client.get("/api/experiments")).json()
            assert result["available"] is False and not result["summaries"]


async def test_real_benchmark_dataset_and_tracker_expiry(
    console_client: tuple[httpx.AsyncClient, Console, SwarmRegistry],
) -> None:
    client, _, registry = console_client
    async with asyncio.timeout(15):
        response = await client.get("/api/experiments")
        data = response.json()
        assert data["available"] is True
        assert len(data["summaries"]) == 8
        assert {row["num_clients"] for row in data["summaries"]} == {1, 2, 4, 8}
        assert all(row["count"] == 5 for row in data["summaries"])
        assert len(data["audit"]) == 48
        assert sum(a["reason"] == "warmup" for a in data["audit"]) == 8
        assert "loopback" in data["caption"]
        snapshot = (await client.get("/api/state")).json()
        assert snapshot["tracker"]["online"] is True
        assert snapshot["tracker"]["swarms"] == []
        assert registry.peer_count() == 0


async def test_manifest_traversal_and_unknown_asset_rejected(
    console_client: tuple[httpx.AsyncClient, Console, SwarmRegistry],
) -> None:
    client, console, _ = console_client
    async with asyncio.timeout(10):
        asset = (await client.post("/api/assets?name=source", content=b"data")).json()
        manifest = (await client.get(f"/api/assets/{asset['id']}/manifest")).json()
        manifest["file_name"] = "../escape"
        response = await client.post(
            "/api/assets?name=unsafe.json&manifest_only=true", content=json.dumps(manifest)
        )
        assert response.status_code == 400
        assert len(console.assets) == 1
        response = await client.post("/api/transfers", json={"asset_id": "0" * 32, "kind": "seed"})
        assert response.status_code == 404


async def test_final_hash_failure_is_explicit_and_output_is_unavailable(
    console_client: tuple[httpx.AsyncClient, Console, SwarmRegistry],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, console, _ = console_client
    original_finalize = StorageManager.finalize

    def corrupt_before_finalization(storage: StorageManager) -> Path:
        with storage.part_path.open("r+b") as stream:
            stream.write(b"corrupt")
        return original_finalize(storage)

    monkeypatch.setattr(StorageManager, "finalize", corrupt_before_finalization)
    async with asyncio.timeout(10):
        asset = (await client.post("/api/assets?name=corrupt", content=b"original data")).json()
        seed = await start_peer(client, asset["id"], "seed")
        await wait_state(console, seed, "seeding")
        key = await start_peer(client, asset["id"], "download")
        task = console.transfers[key].task
        assert task is not None
        await task
        transfer = console.transfers[key].describe()
        assert transfer["state"] == "failed"
        assert transfer["metrics"]["verified_chunks"] == asset["chunk_count"]
        assert transfer["metrics"]["final_integrity"] == "failed"
        assert "SHA-256" in transfer["error"]
        assert (await client.get(f"/api/transfers/{key}/file")).status_code == 409
