"""Integration tests for the Tracker HTTP control plane using ASGITransport."""

from collections.abc import AsyncIterator

import httpx
import pytest

from p2p.tracker.models import AnnounceEvent
from p2p.tracker.registry import SwarmRegistry
from p2p.tracker.server import app, get_registry
from tests.helpers.clock import FakeClock

SAMPLE_SWARM_A = "a" * 64
SAMPLE_SWARM_B = "b" * 64


@pytest.fixture
def fake_clock() -> FakeClock:
    """Fixture providing a controllable clock starting at t=100.0."""
    return FakeClock(100.0)


@pytest.fixture
def isolated_registry(fake_clock: FakeClock) -> SwarmRegistry:
    """Fixture providing an isolated SwarmRegistry instance with fake clock."""
    return SwarmRegistry(clock=fake_clock)


@pytest.fixture
async def client(isolated_registry: SwarmRegistry) -> AsyncIterator[httpx.AsyncClient]:
    """Fixture providing an async HTTP client wired to the isolated registry."""
    previous_override = app.dependency_overrides.get(get_registry)
    app.dependency_overrides[get_registry] = lambda: isolated_registry
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            yield ac
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_registry, None)
        else:
            app.dependency_overrides[get_registry] = previous_override


# ==============================================================================
# 1. Health Endpoint Test
# ==============================================================================


@pytest.mark.asyncio
async def test_health_endpoint(client: httpx.AsyncClient) -> None:
    """Verify existing GET /health returns 200 OK with expected status payload."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "tracker"}


# ==============================================================================
# 2. Started Announcement Test
# ==============================================================================


@pytest.mark.asyncio
async def test_announce_started_success(
    client: httpx.AsyncClient, isolated_registry: SwarmRegistry
) -> None:
    """Verify POST /announce with 'started' registers the peer and returns 200."""
    payload = {
        "swarm_id": SAMPLE_SWARM_A,
        "peer_id": "peer-01",
        "host": "127.0.0.1",
        "port": 6881,
        "event": AnnounceEvent.STARTED.value,
        "is_seeder": False,
    }
    response = await client.post("/announce", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["interval"] == 30
    assert data["peers"] == []  # Caller excluded

    # Verify peer is recorded in the registry
    record = isolated_registry.get_peer(SAMPLE_SWARM_A, "peer-01")
    assert record is not None
    assert record.host == "127.0.0.1"
    assert record.port == 6881
    assert record.is_seeder is False
    assert record.last_seen == 100.0


# ==============================================================================
# 3. Heartbeat Update Test
# ==============================================================================


@pytest.mark.asyncio
async def test_announce_heartbeat_updates_timestamp(
    client: httpx.AsyncClient,
    fake_clock: FakeClock,
    isolated_registry: SwarmRegistry,
) -> None:
    """Verify POST /announce with 'heartbeat' updates last_seen timestamp."""
    # Register initially at t=100.0
    await client.post(
        "/announce",
        json={
            "swarm_id": SAMPLE_SWARM_A,
            "peer_id": "peer-01",
            "host": "127.0.0.1",
            "port": 6881,
            "event": "started",
            "is_seeder": False,
        },
    )

    # Advance clock and send heartbeat
    fake_clock.advance(20.0)
    response = await client.post(
        "/announce",
        json={
            "swarm_id": SAMPLE_SWARM_A,
            "peer_id": "peer-01",
            "host": "127.0.0.2",
            "port": 6889,
            "event": "heartbeat",
        },
    )
    assert response.status_code == 200

    record = isolated_registry.get_peer(SAMPLE_SWARM_A, "peer-01")
    assert record is not None
    assert record.last_seen == 120.0
    assert record.host == "127.0.0.2"
    assert record.port == 6889


# ==============================================================================
# 4. Completed Event Promotes Peer to Seeder
# ==============================================================================


@pytest.mark.asyncio
async def test_announce_completed_promotes_to_seeder(
    client: httpx.AsyncClient, isolated_registry: SwarmRegistry
) -> None:
    """Verify POST /announce with 'completed' marks the peer as a seeder."""
    # Start as leecher
    await client.post(
        "/announce",
        json={
            "swarm_id": SAMPLE_SWARM_A,
            "peer_id": "peer-leecher",
            "host": "127.0.0.1",
            "port": 6881,
            "event": "started",
            "is_seeder": False,
        },
    )
    record = isolated_registry.get_peer(SAMPLE_SWARM_A, "peer-leecher")
    assert record is not None and record.is_seeder is False

    # Announce completion
    response = await client.post(
        "/announce",
        json={
            "swarm_id": SAMPLE_SWARM_A,
            "peer_id": "peer-leecher",
            "host": "127.0.0.1",
            "port": 6881,
            "event": "completed",
        },
    )
    assert response.status_code == 200

    updated = isolated_registry.get_peer(SAMPLE_SWARM_A, "peer-leecher")
    assert updated is not None
    assert updated.is_seeder is True


# ==============================================================================
# 5. Stopped Event Removes Peer
# ==============================================================================


@pytest.mark.asyncio
async def test_announce_stopped_removes_peer(
    client: httpx.AsyncClient, isolated_registry: SwarmRegistry
) -> None:
    """Verify POST /announce with 'stopped' removes the peer from the registry."""
    await client.post(
        "/announce",
        json={
            "swarm_id": SAMPLE_SWARM_A,
            "peer_id": "peer-leaving",
            "host": "127.0.0.1",
            "port": 6881,
            "event": "started",
        },
    )
    assert isolated_registry.peer_count(SAMPLE_SWARM_A) == 1

    response = await client.post(
        "/announce",
        json={
            "swarm_id": SAMPLE_SWARM_A,
            "peer_id": "peer-leaving",
            "host": "127.0.0.1",
            "port": 6881,
            "event": "stopped",
        },
    )
    assert response.status_code == 200
    assert response.json()["peers"] == []
    assert isolated_registry.get_peer(SAMPLE_SWARM_A, "peer-leaving") is None
    assert isolated_registry.peer_count(SAMPLE_SWARM_A) == 0


# ==============================================================================
# 6. Announce Response Excludes Requesting Peer
# ==============================================================================


@pytest.mark.asyncio
async def test_announce_excludes_requesting_peer(client: httpx.AsyncClient) -> None:
    """Verify returned peer lists never contain the announcing peer itself."""
    # Peer 1 announces
    resp1 = await client.post(
        "/announce",
        json={
            "swarm_id": SAMPLE_SWARM_A,
            "peer_id": "peer-1",
            "host": "127.0.0.1",
            "port": 6881,
            "event": "started",
        },
    )
    assert resp1.json()["peers"] == []

    # Peer 2 announces -> sees Peer 1, but NOT Peer 2
    resp2 = await client.post(
        "/announce",
        json={
            "swarm_id": SAMPLE_SWARM_A,
            "peer_id": "peer-2",
            "host": "127.0.0.1",
            "port": 6882,
            "event": "started",
        },
    )
    peers_for_2 = resp2.json()["peers"]
    assert len(peers_for_2) == 1
    assert peers_for_2[0]["peer_id"] == "peer-1"
    assert peers_for_2[0]["port"] == 6881

    # Peer 1 re-announces -> sees Peer 2, but NOT Peer 1
    resp1_again = await client.post(
        "/announce",
        json={
            "swarm_id": SAMPLE_SWARM_A,
            "peer_id": "peer-1",
            "host": "127.0.0.1",
            "port": 6881,
            "event": "heartbeat",
        },
    )
    peers_for_1 = resp1_again.json()["peers"]
    assert len(peers_for_1) == 1
    assert peers_for_1[0]["peer_id"] == "peer-2"
    assert peers_for_1[0]["port"] == 6882


# ==============================================================================
# 7. Peer Listing for a Populated Swarm
# ==============================================================================


@pytest.mark.asyncio
async def test_get_swarm_peers_populated(client: httpx.AsyncClient) -> None:
    """Verify GET /swarms/{swarm_id}/peers lists all active peers in the swarm."""
    await client.post(
        "/announce",
        json={
            "swarm_id": SAMPLE_SWARM_A,
            "peer_id": "peer-seeder",
            "host": "127.0.0.1",
            "port": 6881,
            "event": "started",
            "is_seeder": True,
        },
    )
    await client.post(
        "/announce",
        json={
            "swarm_id": SAMPLE_SWARM_A,
            "peer_id": "peer-leecher",
            "host": "192.168.1.50",
            "port": 6882,
            "event": "started",
            "is_seeder": False,
        },
    )

    response = await client.get(f"/swarms/{SAMPLE_SWARM_A}/peers")
    assert response.status_code == 200

    data = response.json()
    assert data["swarm_id"] == SAMPLE_SWARM_A
    peers = data["peers"]
    assert len(peers) == 2

    by_id = {p["peer_id"]: p for p in peers}
    assert by_id["peer-seeder"]["is_seeder"] is True
    assert by_id["peer-seeder"]["port"] == 6881
    assert by_id["peer-seeder"]["last_seen"] == 100.0
    assert by_id["peer-leecher"]["is_seeder"] is False
    assert by_id["peer-leecher"]["host"] == "192.168.1.50"
    assert by_id["peer-leecher"]["last_seen"] == 100.0


# ==============================================================================
# 8. Unknown Swarm Returns HTTP 200 and Empty Peers
# ==============================================================================


@pytest.mark.asyncio
async def test_get_swarm_peers_unknown_returns_200_empty(
    client: httpx.AsyncClient,
) -> None:
    """Verify GET /swarms/{swarm_id}/peers for an unknown swarm returns 200 with empty list."""
    unknown_swarm_id = "f" * 64
    response = await client.get(f"/swarms/{unknown_swarm_id}/peers")
    assert response.status_code == 200
    data = response.json()
    assert data["swarm_id"] == unknown_swarm_id
    assert data["peers"] == []


@pytest.mark.asyncio
async def test_get_swarm_peers_rejects_malformed_swarm_id(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/swarms/not-a-swarm-id/peers")
    assert response.status_code == 422


# ==============================================================================
# 9. Invalid Request Returns HTTP 422
# ==============================================================================


@pytest.mark.parametrize(
    ("invalid_payload", "error_field"),
    [
        (
            {  # Invalid port out of range
                "swarm_id": SAMPLE_SWARM_A,
                "peer_id": "peer-01",
                "host": "127.0.0.1",
                "port": 99999,
                "event": "started",
            },
            "port",
        ),
        (
            {  # Invalid swarm_id (not 64 hex)
                "swarm_id": "not-64-hex",
                "peer_id": "peer-01",
                "host": "127.0.0.1",
                "port": 6881,
                "event": "started",
            },
            "swarm_id",
        ),
        (
            {  # Invalid event enum
                "swarm_id": SAMPLE_SWARM_A,
                "peer_id": "peer-01",
                "host": "127.0.0.1",
                "port": 6881,
                "event": "unknown_event",
            },
            "event",
        ),
        (
            {  # Invalid host syntax
                "swarm_id": SAMPLE_SWARM_A,
                "peer_id": "peer-01",
                "host": "999.999.999.999",
                "port": 6881,
                "event": "started",
            },
            "host",
        ),
        (
            {  # Missing required peer_id
                "swarm_id": SAMPLE_SWARM_A,
                "host": "127.0.0.1",
                "port": 6881,
                "event": "started",
            },
            "peer_id",
        ),
    ],
)
@pytest.mark.asyncio
async def test_announce_invalid_request_returns_422(
    client: httpx.AsyncClient,
    invalid_payload: dict[str, object],
    error_field: str,
) -> None:
    """Verify invalid payloads return HTTP 422 Unprocessable Entity."""
    response = await client.post("/announce", json=invalid_payload)
    assert response.status_code == 422
    assert any(error_field in error["loc"] for error in response.json()["detail"])


# ==============================================================================
# 10. Unexpected JSON Fields Return HTTP 422
# ==============================================================================


@pytest.mark.asyncio
async def test_announce_unexpected_fields_return_422(
    client: httpx.AsyncClient,
) -> None:
    """Verify that sending extra unexpected fields in JSON body returns HTTP 422."""
    payload = {
        "swarm_id": SAMPLE_SWARM_A,
        "peer_id": "peer-01",
        "host": "127.0.0.1",
        "port": 6881,
        "event": "started",
        "unexpected_extra_field": "forbidden_data",
    }
    response = await client.post("/announce", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
