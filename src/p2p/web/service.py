"""Bounded asset storage and ownership of console peer tasks."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from p2p.config import (
    DEFAULT_CHUNK_SIZE,
    WEB_MAX_ACTIVE_TRANSFERS,
    WEB_MAX_ASSETS,
    WEB_MAX_CONCURRENT_IMPORTS,
    WEB_MAX_FILE_BYTES,
    WEB_MAX_TRANSFERS,
    WEB_TRACKER_TIMEOUT_SEC,
    WEB_UPLOAD_TIMEOUT_SEC,
)
from p2p.peer.client import SwarmPeer
from p2p.storage.manager import validate_safe_filename
from p2p.storage.manifest import (
    MAX_MANIFEST_SIZE,
    FileManifest,
    build_manifest,
    compute_swarm_id,
    load_manifest,
    write_manifest,
)

logger = logging.getLogger(__name__)


class StartTransfer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    asset_id: str = Field(min_length=32, max_length=32, pattern=r"^[a-f0-9]+$")
    kind: Literal["seed", "download"]
    upload_rate_limit: float | None = Field(default=None, ge=1, le=1024**3, allow_inf_nan=False)
    download_only: bool = False


@dataclass(frozen=True)
class Asset:
    id: str
    manifest: FileManifest
    manifest_path: Path
    source: Path | None
    swarm_id: str

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file_name": self.manifest["file_name"],
            "file_size": self.manifest["file_size"],
            "chunk_count": self.manifest["chunk_count"],
            "chunk_size": self.manifest["chunk_size"],
            "file_sha256": self.manifest["file_sha256"],
            "swarm_id": self.swarm_id,
            "can_seed": self.source is not None,
        }


@dataclass
class Transfer:
    id: str
    asset: Asset
    options: StartTransfer
    state: str = "starting"
    error: str | None = None
    peer: SwarmPeer | None = None
    task: asyncio.Task[None] | None = None
    stop_task: asyncio.Task[None] | None = None
    output: Path | None = None

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "asset_id": self.asset.id,
            "file_name": self.asset.manifest["file_name"],
            "file_size": self.asset.manifest["file_size"],
            "chunk_count": self.asset.manifest["chunk_count"],
            "file_sha256": self.asset.manifest["file_sha256"],
            "kind": self.options.kind,
            "download_only": self.options.download_only,
            "upload_rate_limit": self.options.upload_rate_limit,
            "state": self.state,
            "error": self.error,
            "has_output": self.output is not None,
            "metrics": asdict(self.peer.snapshot()) if self.peer else None,
        }


async def finish_disk_task[T](task: asyncio.Task[T]) -> T:
    """Join thread work even on cancellation, before a caller cleans its files."""
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.gather(task, return_exceptions=True)
        raise


class Console:
    """Own imported assets, peer lifecycles and cleanup on one event loop."""

    def __init__(
        self,
        workspace: Path,
        tracker_url: str,
        tracker_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self.tracker_url = tracker_url.rstrip("/")
        self.tracker_transport = tracker_transport
        self.assets: dict[str, Asset] = {}
        self.transfers: dict[str, Transfer] = {}
        self._imports = 0
        self._closed = False

    def _directory(self, relative: Path) -> Path:
        candidate = self.workspace / relative
        resolved = candidate.resolve()
        if resolved != candidate or not resolved.is_relative_to(self.workspace):
            raise ValueError("workspace subdirectories must not be symbolic links")
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate

    async def import_asset(self, request: Request, name: str, manifest_only: bool) -> Asset:
        if self._closed:
            raise HTTPException(503, "Console is shutting down")
        if (
            len(self.assets) + self._imports >= WEB_MAX_ASSETS
            or self._imports >= WEB_MAX_CONCURRENT_IMPORTS
        ):
            raise HTTPException(
                429, "Asset or concurrent import limit reached; restart to clear history"
            )
        self._imports += 1
        path: Path | None = None
        try:
            asset_id = uuid.uuid4().hex
            directory = await finish_disk_task(
                asyncio.create_task(asyncio.to_thread(self._directory, Path("assets") / asset_id))
            )
            path = validate_safe_filename(directory, name)
            limit = MAX_MANIFEST_SIZE if manifest_only else WEB_MAX_FILE_BYTES
            total = 0
            async with asyncio.timeout(WEB_UPLOAD_TIMEOUT_SEC):
                with path.open("xb") as stream:
                    async for chunk in request.stream():
                        total += len(chunk)
                        if total > limit:
                            raise HTTPException(413, f"Upload exceeds {limit} bytes")
                        await finish_disk_task(
                            asyncio.create_task(asyncio.to_thread(stream.write, chunk))
                        )
            if manifest_only:
                manifest = await finish_disk_task(
                    asyncio.create_task(asyncio.to_thread(load_manifest, path))
                )
                source = None
                manifest_path = path
            else:
                manifest = await finish_disk_task(
                    asyncio.create_task(asyncio.to_thread(build_manifest, path, DEFAULT_CHUNK_SIZE))
                )
                source = path
                manifest_path = directory / "manifest.json"
                # Keep the manifest separate even when the selected file is named manifest.json.
                if manifest_path == source:
                    manifest_path = directory / "generated.manifest.json"
                await finish_disk_task(
                    asyncio.create_task(asyncio.to_thread(write_manifest, manifest, manifest_path))
                )
            asset = Asset(asset_id, manifest, manifest_path, source, compute_swarm_id(manifest))
            self.assets[asset_id] = asset
            return asset
        except BaseException:
            if path is not None:
                await asyncio.to_thread(path.unlink, missing_ok=True)
            raise
        finally:
            self._imports -= 1

    def start(self, options: StartTransfer) -> Transfer:
        if self._closed:
            raise HTTPException(503, "Console is shutting down")
        asset = self.assets.get(options.asset_id)
        if asset is None:
            raise HTTPException(404, "Unknown asset")
        if options.kind == "seed" and (asset.source is None or options.download_only):
            raise HTTPException(422, "Seeding requires a source file and uploads enabled")
        if asset.manifest["file_size"] > WEB_MAX_FILE_BYTES:
            raise HTTPException(413, "File exceeds console size limit; use the existing CLI")
        active = sum(t.task is not None and not t.task.done() for t in self.transfers.values())
        if len(self.transfers) >= WEB_MAX_TRANSFERS or active >= WEB_MAX_ACTIVE_TRANSFERS:
            raise HTTPException(
                429, "Transfer limit reached; stop peers or restart to clear history"
            )
        transfer = Transfer(uuid.uuid4().hex, asset, options)
        self.transfers[transfer.id] = transfer
        transfer.task = asyncio.create_task(self._run(transfer), name=f"console-{transfer.id}")
        return transfer

    async def _run(self, transfer: Transfer) -> None:
        try:
            directory = await finish_disk_task(
                asyncio.create_task(
                    asyncio.to_thread(self._directory, Path("transfers") / transfer.id)
                )
            )
            peer = SwarmPeer(
                transfer.asset.manifest,
                self.tracker_url,
                directory,
                seed_file=transfer.asset.source if transfer.options.kind == "seed" else None,
                tracker_transport=self.tracker_transport,
                tracker_timeout=WEB_TRACKER_TIMEOUT_SEC,
                upload_enabled=not transfer.options.download_only,
                upload_rate_limit=transfer.options.upload_rate_limit,
            )
            transfer.peer = peer
            await peer.start()
            if transfer.options.kind == "download":
                transfer.state = "downloading"
                transfer.output = await peer.download()
                transfer.state = "completed"
            else:
                transfer.state = "seeding"
            await peer.wait_until_stopped()
        except asyncio.CancelledError:
            transfer.state = "stopped"
            raise
        except Exception as exc:
            transfer.error = str(exc) or type(exc).__name__
            transfer.state = "failed"
            logger.exception("Console transfer %s failed", transfer.id)
        finally:
            if transfer.peer is not None:
                try:
                    await transfer.peer.close()
                except Exception as exc:
                    transfer.error = f"Cleanup failed: {exc}"
                    transfer.state = "failed"
                    logger.exception("Console peer cleanup failed")

    async def stop(self, transfer_id: str) -> None:
        transfer = self.transfers.get(transfer_id)
        if transfer is None:
            raise HTTPException(404, "Unknown transfer")
        if transfer.stop_task is None:
            transfer.stop_task = asyncio.create_task(
                self._stop_transfer(transfer), name=f"console-stop-{transfer.id}"
            )
        await asyncio.shield(transfer.stop_task)

    async def _stop_transfer(self, transfer: Transfer) -> None:
        if transfer.task is not None and not transfer.task.done():
            transfer.task.cancel()
            await asyncio.gather(transfer.task, return_exceptions=True)
            # A task cancelled before its first instruction never runs its finally block.
            if transfer.state == "starting":
                transfer.state = "stopped"

    async def close(self) -> None:
        self._closed = True
        await asyncio.gather(*(self.stop(key) for key in self.transfers))
