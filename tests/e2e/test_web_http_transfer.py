"""Separate tracker and two console processes over real HTTP and peer TCP."""

from __future__ import annotations

import asyncio
import hashlib
import multiprocessing
import socket
import time
from collections.abc import Iterator
from contextlib import contextmanager
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

import httpx
import uvicorn


def serve_process(pipe: Connection, workspace: str | None, tracker_url: str | None) -> None:
    """Publish an ephemeral socket address; a pipe message requests graceful exit."""
    from p2p.tracker.server import app
    from p2p.web.app import create_app

    application = app if workspace is None else create_app(Path(workspace), str(tracker_url))
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    pipe.send(listener.getsockname()[1])

    async def run() -> None:
        server = uvicorn.Server(uvicorn.Config(application, log_level="error"))

        async def shutdown_signal() -> None:
            await asyncio.to_thread(pipe.recv)
            server.should_exit = True

        watcher = asyncio.create_task(shutdown_signal())
        try:
            await server.serve(sockets=[listener])
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)

    try:
        asyncio.run(run())
    finally:
        listener.close()
        pipe.close()


@contextmanager
def http_server(workspace: Path | None = None, tracker_url: str | None = None) -> Iterator[str]:
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=serve_process,
        args=(child, str(workspace) if workspace else None, tracker_url),
    )
    process.start()
    child.close()
    try:
        assert parent.poll(15), "server did not publish its port"
        url = f"http://127.0.0.1:{parent.recv()}"
        deadline = time.monotonic() + 15
        with httpx.Client(timeout=1, trust_env=False) as client:
            while True:
                try:
                    if client.get(url + ("/" if workspace else "/health")).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                assert time.monotonic() < deadline, "server never became ready"
                assert process.is_alive(), "server exited during startup"
                time.sleep(0.02)
        yield url
    finally:
        if process.is_alive():
            parent.send("stop")
        process.join(15)
        if process.is_alive():
            process.terminate()
            process.join(5)
            raise AssertionError("server required forced termination")
        parent.close()
        assert process.exitcode == 0


def peer_state(client: httpx.Client, key: str, expected: str) -> dict[str, Any]:
    deadline = time.monotonic() + 15
    while True:
        response = client.get("/api/state")
        response.raise_for_status()
        transfer = next(t for t in response.json()["transfers"] if t["id"] == key)
        assert transfer["state"] != "failed", transfer["error"]
        if transfer["state"] == expected:
            return dict(transfer)
        assert time.monotonic() < deadline, f"peer did not reach {expected}"
        time.sleep(0.01)


def new_peer(client: httpx.Client, asset_id: str, kind: str, **options: Any) -> str:
    response = client.post("/api/transfers", json={"asset_id": asset_id, "kind": kind, **options})
    assert response.status_code == 202, response.text
    return str(response.json()["id"])


def test_two_consoles_http_tracker_tcp_relay_and_baseline(tmp_path: Path) -> None:
    with http_server() as tracker:
        with (
            http_server(tmp_path / "origin-console", tracker) as origin_url,
            http_server(tmp_path / "client-console", tracker) as client_url,
        ):
            headers = {"X-P2P-UI": "1"}
            with (
                httpx.Client(
                    base_url=origin_url, headers=headers, timeout=10, trust_env=False
                ) as origin,
                httpx.Client(
                    base_url=client_url, headers=headers, timeout=10, trust_env=False
                ) as client,
            ):
                contents = bytes(range(256)) * 4096  # 1 MiB, generated locally.
                imported = origin.post("/api/assets?name=http-demo.bin", content=contents)
                assert imported.status_code == 201
                asset_id = imported.json()["id"]
                manifest = origin.get(f"/api/assets/{asset_id}/manifest")
                imported_manifest = client.post(
                    "/api/assets?name=manifest.json&manifest_only=true", content=manifest.content
                )
                assert imported_manifest.status_code == 201
                remote_asset = imported_manifest.json()["id"]
                seed = new_peer(origin, asset_id, "seed", upload_rate_limit=524288.0)
                peer_state(origin, seed, "seeding")
                first = new_peer(client, remote_asset, "download")
                result = peer_state(client, first, "completed")
                assert result["metrics"]["final_integrity"] == "verified"
                assert result["metrics"]["duration_seconds"] >= 0.8
                assert (
                    hashlib.sha256(client.get(f"/api/transfers/{first}/file").content).hexdigest()
                    == manifest.json()["file_sha256"]
                )
                assert origin.post(f"/api/transfers/{seed}/stop").status_code == 200
                second = new_peer(client, remote_asset, "download")
                relay = peer_state(client, second, "completed")
                assert relay["metrics"]["downloaded_from"] == {
                    result["metrics"]["peer_id"]: len(contents)
                }
                assert client.get(f"/api/transfers/{second}/file").content == contents
                for key in (first, second):
                    assert client.post(f"/api/transfers/{key}/stop").status_code == 200

                baseline_seed = new_peer(origin, asset_id, "seed")
                source = peer_state(origin, baseline_seed, "seeding")
                clients = [
                    new_peer(client, remote_asset, "download", download_only=True) for _ in range(2)
                ]
                for key in clients:
                    baseline = peer_state(client, key, "completed")
                    assert baseline["metrics"]["bytes_uploaded"] == 0
                    assert baseline["metrics"]["upload_enabled"] is False
                    assert baseline["metrics"]["downloaded_from"] == {
                        source["metrics"]["peer_id"]: len(contents)
                    }
                    assert client.get(f"/api/transfers/{key}/file").content == contents
                benchmarks = client.get("/api/experiments").json()
                assert benchmarks["available"] and len(benchmarks["summaries"]) == 8
                assert all(summary["count"] == 5 for summary in benchmarks["summaries"])
                # Leave baseline peers alive: console process shutdown must deregister them.
            # Inner console contexts exit first, before the tracker.
        with httpx.Client(timeout=3, trust_env=False) as observer:
            response = observer.get(f"{tracker}/swarms")
            assert response.status_code == 200 and response.json() == []
    # Every context above requires a clean exit code, without forced termination.
