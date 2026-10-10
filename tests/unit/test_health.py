"""Unit tests for Tracker HTTP endpoints."""

from fastapi.testclient import TestClient

from p2p.tracker.server import app

client = TestClient(app)


def test_tracker_health_endpoint() -> None:
    """Verify tracker /health endpoint returns 200 OK and expected status JSON."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "tracker"}
