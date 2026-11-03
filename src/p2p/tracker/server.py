"""FastAPI application for the Tracker HTTP control plane."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI, Path, status

from p2p.protocol.messages import HEX_64_PATTERN
from p2p.tracker.models import (
    AnnounceRequest,
    AnnounceResponse,
    SwarmPeersResponse,
)
from p2p.tracker.registry import SwarmRegistry

_registry = SwarmRegistry()


def get_registry() -> SwarmRegistry:
    """Dependency provider returning the active SwarmRegistry instance."""
    return _registry


app = FastAPI(
    title="P2P Swarm Tracker",
    description="HTTP Control Plane for Peer Discovery and Swarm Management",
    version="0.1.0",
)


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check() -> dict[str, Any]:
    """Basic health check endpoint returning server status."""
    return {"status": "ok", "service": "tracker"}


@app.post("/announce", response_model=AnnounceResponse, status_code=status.HTTP_200_OK)
async def announce(
    request: AnnounceRequest,
    registry: Annotated[SwarmRegistry, Depends(get_registry)],
) -> AnnounceResponse:
    """Process a peer announcement and return active peers in the swarm."""
    return registry.announce(request)


@app.get(
    "/swarms/{swarm_id}/peers",
    response_model=SwarmPeersResponse,
    status_code=status.HTTP_200_OK,
)
async def get_swarm_peers(
    swarm_id: Annotated[str, Path(pattern=HEX_64_PATTERN.pattern)],
    registry: Annotated[SwarmRegistry, Depends(get_registry)],
) -> SwarmPeersResponse:
    """Return active peers for the requested swarm, or empty list if unknown."""
    peers = registry.get_swarm_peers(swarm_id)
    return SwarmPeersResponse(swarm_id=swarm_id, peers=peers)
