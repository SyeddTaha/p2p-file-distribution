"""Command-line entry point for the tracker and swarm peers."""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path

import httpx
import uvicorn

from p2p.peer.client import SwarmPeer
from p2p.peer.downloader import DownloadError
from p2p.storage.manifest import build_manifest, load_manifest, write_manifest

logger = logging.getLogger("p2p")


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(prog="p2p")
    commands = parser.add_subparsers(dest="command", required=True)

    tracker = commands.add_parser("tracker-start", help="run the HTTP tracker")
    tracker.add_argument("--host", default="127.0.0.1")
    tracker.add_argument("--port", type=int, default=8000)

    manifest = commands.add_parser("create-manifest", help="hash a file into a manifest")
    manifest.add_argument("file_path", type=Path)
    manifest.add_argument("--chunk-size", type=int, default=None)
    manifest.add_argument("--output", type=Path, default=None)

    seeder = commands.add_parser("seed-file", help="serve a verified file in a swarm")
    seeder.add_argument("manifest_path", type=Path)
    seeder.add_argument("file_path", type=Path)
    seeder.add_argument("--tracker-url", required=True)
    seeder.add_argument("--listen-port", type=int, default=0)
    seeder.add_argument("--host", default="127.0.0.1")

    downloader = commands.add_parser("download-file", help="download and seed a swarm file")
    downloader.add_argument("manifest_path", type=Path)
    downloader.add_argument("--download-dir", type=Path, required=True)
    downloader.add_argument("--tracker-url", required=True)
    downloader.add_argument("--listen-port", type=int, default=0)
    downloader.add_argument("--host", default="127.0.0.1")
    downloader.add_argument(
        "--no-upload",
        action="store_true",
        help="disable chunk advertising and uploading for the client-server baseline",
    )
    return parser


async def _run_peer_command(args: argparse.Namespace) -> None:
    if args.command == "create-manifest":
        if args.chunk_size is None:
            manifest = await asyncio.to_thread(build_manifest, args.file_path)
        else:
            manifest = await asyncio.to_thread(build_manifest, args.file_path, args.chunk_size)
        output_path = args.output or Path(f"{args.file_path}.manifest.json")
        await asyncio.to_thread(write_manifest, manifest, output_path)
        print(f"Created manifest: {output_path}")
        return

    manifest = await asyncio.to_thread(load_manifest, args.manifest_path)
    if args.command == "seed-file":
        peer = SwarmPeer(
            manifest,
            args.tracker_url,
            args.file_path.parent,
            seed_file=args.file_path,
            host=args.host,
            listen_port=args.listen_port,
        )
        async with peer:
            logger.info("Seeding swarm %s on %s:%d", peer.swarm_id, peer.host, peer.listen_port)
            await peer.wait_until_stopped()
        return

    peer = SwarmPeer(
        manifest,
        args.tracker_url,
        args.download_dir,
        host=args.host,
        listen_port=args.listen_port,
        upload_enabled=not args.no_upload,
    )
    async with peer:
        final_path = await peer.download()
        print(f"Downloaded and verified: {final_path}")
        if args.no_upload:
            logger.info("Download-only peer remains online; press Ctrl+C to stop")
        else:
            logger.info("Continuing to seed swarm %s; press Ctrl+C to stop", peer.swarm_id)
        await peer.wait_until_stopped()


def main(argv: Sequence[str] | None = None) -> None:
    """Run the selected CLI command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        if args.command == "tracker-start":
            if not 1 <= args.port <= 65535:
                parser.error("--port must be in 1..65535")
            uvicorn.run("p2p.tracker.server:app", host=args.host, port=args.port)
            return
        asyncio.run(_run_peer_command(args))
    except KeyboardInterrupt:
        logger.info("Shutting down")
    except (DownloadError, OSError, ValueError, httpx.HTTPError) as exc:
        message = str(exc) or type(exc).__name__
        parser.exit(1, f"{parser.prog}: error: {message}\n")


if __name__ == "__main__":
    main()
