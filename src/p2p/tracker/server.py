"""FastAPI application for the Tracker HTTP control plane."""

from typing import Any

from fastapi import FastAPI, status

app = FastAPI(
    title="P2P Swarm Tracker",
    description="HTTP Control Plane for Peer Discovery and Swarm Management",
    version="0.1.0",
)


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check() -> dict[str, Any]:
    """Basic health check endpoint returning server status."""
    return {"status": "ok", "service": "tracker"}
