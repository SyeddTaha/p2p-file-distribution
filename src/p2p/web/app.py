"""Local HTTP UI; file distribution continues through peer TCP sockets."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from p2p.config import (
    WEB_MAX_SETTINGS_BYTES,
    WEB_MAX_TRACKER_RESPONSE_BYTES,
    WEB_TRACKER_TIMEOUT_SEC,
)
from p2p.tracker.models import SwarmPeersResponse
from p2p.web.experiments import read_experiments
from p2p.web.service import Console, StartTransfer

STATIC = Path(__file__).parent / "static"


async def tracker_json(client: httpx.AsyncClient, url: str) -> Any:
    """Bound response bytes before parsing untrusted tracker JSON."""
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        raw = bytearray()
        async for chunk in response.aiter_bytes():
            raw.extend(chunk)
            if len(raw) > WEB_MAX_TRACKER_RESPONSE_BYTES:
                raise ValueError("Tracker response is too large")
    return json.loads(raw)


def create_app(
    workspace: Path = Path("downloads/web-console"),
    tracker_url: str = "http://127.0.0.1:8000",
    *,
    tracker_transport: httpx.AsyncBaseTransport | None = None,
    benchmark_csv: Path | None = None,
) -> FastAPI:
    """Create an isolated console. Only startup configuration selects local paths."""
    parsed = urlsplit(tracker_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username:
        raise ValueError("tracker URL must be an HTTP(S) address without credentials")
    console = Console(workspace, tracker_url, tracker_transport)
    csv_path = (
        benchmark_csv or Path(__file__).resolve().parents[3] / "bench/results/experiments.csv"
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(
            transport=tracker_transport,
            timeout=WEB_TRACKER_TIMEOUT_SEC,
            trust_env=False,
        ) as client:
            app.state.tracker_client = client
            try:
                yield
            finally:
                await console.close()

    app = FastAPI(title="Local P2P console", lifespan=lifespan)
    app.state.console = console
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])

    @app.middleware("http")
    async def local_guard(request: Request, call_next: Any) -> Response:
        origin = request.headers.get("origin")
        if origin is not None and origin != f"{request.url.scheme}://{request.headers.get('host')}":
            return JSONResponse(
                {"detail": "Cross-origin console access is disabled"}, status_code=403
            )
        if request.method not in ("GET", "HEAD") and request.headers.get("x-p2p-ui") != "1":
            return JSONResponse({"detail": "Console action header required"}, status_code=403)
        try:
            response: Response = await call_next(request)
        except (ValueError, OSError, TimeoutError) as exc:
            return JSONResponse({"detail": str(exc) or type(exc).__name__}, status_code=400)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/state")
    async def state(request: Request) -> dict[str, Any]:
        tracker: dict[str, Any] = {"online": False, "url": console.tracker_url, "swarms": None}
        try:
            async with asyncio.timeout(WEB_TRACKER_TIMEOUT_SEC):
                health = await tracker_json(
                    request.app.state.tracker_client, f"{console.tracker_url}/health"
                )
                if (
                    not isinstance(health, dict)
                    or health.get("status") != "ok"
                    or health.get("service") != "tracker"
                ):
                    raise ValueError("Unexpected tracker health response")
                tracker["online"] = True
                swarms = await tracker_json(
                    request.app.state.tracker_client, f"{console.tracker_url}/swarms"
                )
                validated = TypeAdapter(list[SwarmPeersResponse]).validate_python(swarms)
                tracker["swarms"] = [item.model_dump() for item in validated]
        except (httpx.HTTPError, ValueError, TimeoutError) as exc:
            tracker["error"] = str(exc) or type(exc).__name__
        return {
            "tracker": tracker,
            "assets": [asset.describe() for asset in console.assets.values()],
            "transfers": [transfer.describe() for transfer in console.transfers.values()],
        }

    @app.post("/api/assets", status_code=201)
    async def import_asset(
        request: Request, name: str, manifest_only: bool = False
    ) -> dict[str, Any]:
        asset = await console.import_asset(request, name, manifest_only)
        return asset.describe()

    @app.get("/api/assets/{asset_id}/manifest")
    async def manifest(asset_id: str) -> FileResponse:
        asset = console.assets.get(asset_id)
        if asset is None:
            raise HTTPException(404, "Unknown asset")
        return FileResponse(
            asset.manifest_path, filename=f"{asset.manifest['file_name']}.manifest.json"
        )

    @app.post("/api/transfers", status_code=202)
    async def start(request: Request) -> dict[str, Any]:
        body = bytearray()
        async with asyncio.timeout(WEB_TRACKER_TIMEOUT_SEC):
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > WEB_MAX_SETTINGS_BYTES:
                    raise HTTPException(413, "Transfer settings too large")
        try:
            options = StartTransfer.model_validate_json(body)
        except ValidationError as exc:
            raise HTTPException(422, str(exc)) from exc
        return console.start(options).describe()

    @app.post("/api/transfers/{transfer_id}/stop")
    async def stop(transfer_id: str) -> dict[str, str]:
        await console.stop(transfer_id)
        return {"status": "stopped"}

    @app.get("/api/transfers/{transfer_id}/file")
    async def output(transfer_id: str) -> FileResponse:
        transfer = console.transfers.get(transfer_id)
        if transfer is None:
            raise HTTPException(404, "Unknown transfer")
        if transfer.output is None:
            raise HTTPException(409, "No verified output is available")
        return FileResponse(transfer.output, filename=transfer.asset.manifest["file_name"])

    @app.get("/api/experiments")
    async def experiments() -> dict[str, Any]:
        return await asyncio.to_thread(read_experiments, csv_path)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
