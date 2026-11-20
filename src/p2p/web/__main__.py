"""Run independently of the unchanged p2p CLI: python -m p2p.web."""

import argparse
from pathlib import Path

import uvicorn

from p2p.web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Local P2P web console")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--tracker-url", default="http://127.0.0.1:8000")
    parser.add_argument("--workspace", type=Path, default=Path("downloads/web-console"))
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be in 1..65535")
    uvicorn.run(create_app(args.workspace, args.tracker_url), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
