"""Unit tests for Tracker Pydantic models and SwarmRegistry."""

import random

import pytest
from pydantic import ValidationError

from p2p.config import DEFAULT_HEARTBEAT_INTERVAL_SEC
from p2p.tracker.models import (
    AnnounceEvent,
    AnnounceRequest,
    AnnounceResponse,
    PeerInfo,
    SwarmPeerInfo,
    SwarmPeersResponse,
)
from p2p.tracker.registry import MonotonicClock, SwarmRegistry
from tests.helpers.clock import FakeClock

SAMPLE_SWARM_A = "a" * 64
SAMPLE_SWARM_B = "b" * 64


# ==============================================================================
# 1. Pydantic Model Validation Tests
# ==============================================================================


def test_announce_request_valid() -> None:
    req = AnnounceRequest(
        swarm_id=SAMPLE_SWARM_A,
        peer_id="peer-valid-01.local_123",
        host="192.168.1.100",
        port=6881,
        event=AnnounceEvent.STARTED,
        is_seeder=False,
    )
    assert req.swarm_id == SAMPLE_SWARM_A
    assert req.peer_id == "peer-valid-01.local_123"
    assert req.host == "192.168.1.100"
    assert req.port == 6881
    assert req.event == AnnounceEvent.STARTED
    assert req.is_seeder is False


def test_announce_request_event_from_string() -> None:
    req = AnnounceRequest(
        swarm_id=SAMPLE_SWARM_A,
        peer_id="peer-01",
        host="127.0.0.1",
        port=6881,
        event="completed",  # type: ignore[arg-type]
    )
    assert req.event == AnnounceEvent.COMPLETED


@pytest.mark.parametrize(
    "valid_host",
    [
        "127.0.0.1",
        "192.168.1.1",
        "::1",
        "[::1]",
        "2001:db8::1",
        "[2001:db8::1]",
        "localhost",
        "localhost.",
        "node-01.lan",
        "tracker.p2p.test",
        "sub-domain.example.org",
        "a.b.c",
        "a",
        "a" * 63,
        "example.123",
        "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "d" * 61,
        "example.com.",
        "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "d" * 61 + ".",
    ],
)
def test_announce_request_valid_hosts(valid_host: str) -> None:
    req = AnnounceRequest(
        swarm_id=SAMPLE_SWARM_A,
        peer_id="peer-01",
        host=valid_host,
        port=6881,
        event=AnnounceEvent.STARTED,
    )
    assert req.host == valid_host


@pytest.mark.parametrize(
    "invalid_swarm_id",
    [
        "",
        "a" * 63,
        "a" * 65,
        "A" * 64,  # Uppercase hex rejected
        "g" * 64,  # Non-hex character rejected
        12345,
    ],
)
def test_announce_request_invalid_swarm_id(invalid_swarm_id: object) -> None:
    with pytest.raises(ValidationError):
        AnnounceRequest(
            swarm_id=invalid_swarm_id,  # type: ignore[arg-type]
            peer_id="peer-01",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
        )


@pytest.mark.parametrize(
    "invalid_peer_id",
    [
        "",
        "x" * 65,
        "peer with space",
        "peer@special!",
        "peer/slash",
        123,
    ],
)
def test_announce_request_invalid_peer_id(invalid_peer_id: object) -> None:
    with pytest.raises(ValidationError):
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id=invalid_peer_id,  # type: ignore[arg-type]
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
        )


@pytest.mark.parametrize(
    "invalid_host",
    [
        "",
        " " * 10,
        "host with space",
        "999.999.999.999",  # Invalid IPv4
        "256.0.0.1",  # Invalid IPv4 octet
        "1:2:3:4:5:6:7:8:9",  # Invalid IPv6
        "invalid:ipv6:here",
        "-invalid.com",  # Leading hyphen in label
        "invalid-.com",  # Trailing hyphen in label
        "-" + "a" * 62 + ".com",  # Label starts with a hyphen
        "a" * 62 + "-.com",  # Label ends with a hyphen
        "inv_alid.com",  # Underscore forbidden in hostname
        "foo..bar",  # Consecutive dots / empty label
        "1234",  # All numeric hostname
        "a" * 64,  # Label exceeds 63 characters
        "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "d" * 62,
        "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "d" * 61 + "..",
        "host\x00nul",
        "x" * 256,
        127001,
    ],
)
def test_announce_request_invalid_host(invalid_host: object) -> None:
    with pytest.raises(ValidationError):
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-01",
            host=invalid_host,  # type: ignore[arg-type]
            port=6881,
            event=AnnounceEvent.STARTED,
        )


@pytest.mark.parametrize(
    "invalid_port",
    [
        0,
        -1,
        65536,
        70000,
        True,  # Boolean is not an integer port
        False,
        "6881",
        6881.5,
    ],
)
def test_announce_request_invalid_port(invalid_port: object) -> None:
    with pytest.raises(ValidationError):
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-01",
            host="127.0.0.1",
            port=invalid_port,  # type: ignore[arg-type]
            event=AnnounceEvent.STARTED,
        )


@pytest.mark.parametrize(
    "invalid_is_seeder",
    [
        1,
        0,
        "true",
        "false",
        None,
    ],
)
def test_announce_request_invalid_is_seeder(invalid_is_seeder: object) -> None:
    with pytest.raises(ValidationError):
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-01",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
            is_seeder=invalid_is_seeder,  # type: ignore[arg-type]
        )


def test_announce_request_invalid_event() -> None:
    with pytest.raises(ValidationError):
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-01",
            host="127.0.0.1",
            port=6881,
            event="paused",  # type: ignore[arg-type]
        )


def test_announce_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs are not permitted"):
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-01",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
            unexpected_extra="disallowed",  # type: ignore[call-arg]
        )


def test_models_serialization() -> None:
    info = PeerInfo(peer_id="peer-1", host="127.0.0.1", port=6881)
    resp = AnnounceResponse(interval=30, peers=[info])
    data = resp.model_dump()
    assert data == {
        "interval": 30,
        "peers": [{"peer_id": "peer-1", "host": "127.0.0.1", "port": 6881}],
    }

    swarm_info = SwarmPeerInfo(
        peer_id="peer-1",
        host="127.0.0.1",
        port=6881,
        last_seen=100.5,
        is_seeder=True,
    )
    swarm_resp = SwarmPeersResponse(swarm_id=SAMPLE_SWARM_A, peers=[swarm_info])
    assert swarm_resp.model_dump()["peers"][0]["is_seeder"] is True


# ==============================================================================
# 2. Clock Implementation Tests
# ==============================================================================


def test_monotonic_clock() -> None:
    clock = MonotonicClock()
    t1 = clock.now()
    assert isinstance(t1, float)
    assert t1 >= 0


def test_fake_clock_operations() -> None:
    clock = FakeClock(10.0)
    assert clock.now() == 10.0

    clock.advance(5.5)
    assert clock.now() == 15.5

    with pytest.raises(ValueError, match="backwards"):
        clock.advance(-1.0)

    clock.set(100.0)
    assert clock.now() == 100.0


# ==============================================================================
# 3. SwarmRegistry Announcement Event Tests
# ==============================================================================


def test_announce_started_creates_record() -> None:
    clock = FakeClock(100.0)
    registry = SwarmRegistry(clock=clock)

    req = AnnounceRequest(
        swarm_id=SAMPLE_SWARM_A,
        peer_id="peer-01",
        host="127.0.0.1",
        port=6881,
        event=AnnounceEvent.STARTED,
    )
    response = registry.announce(req)

    assert response.interval == DEFAULT_HEARTBEAT_INTERVAL_SEC
    assert response.peers == []  # Caller excluded

    record = registry.get_peer(SAMPLE_SWARM_A, "peer-01")
    assert record is not None
    assert record.peer_id == "peer-01"
    assert record.host == "127.0.0.1"
    assert record.port == 6881
    assert record.last_seen == 100.0
    assert record.is_seeder is False


def test_announce_started_with_is_seeder() -> None:
    clock = FakeClock(50.0)
    registry = SwarmRegistry(clock=clock)

    req = AnnounceRequest(
        swarm_id=SAMPLE_SWARM_A,
        peer_id="peer-seeder",
        host="127.0.0.1",
        port=6881,
        event=AnnounceEvent.STARTED,
        is_seeder=True,
    )
    registry.announce(req)

    record = registry.get_peer(SAMPLE_SWARM_A, "peer-seeder")
    assert record is not None
    assert record.is_seeder is True


def test_announce_heartbeat_refreshes_timestamp() -> None:
    clock = FakeClock(100.0)
    registry = SwarmRegistry(clock=clock)

    # Initial registration
    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-01",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
            is_seeder=True,
        )
    )

    # Advance clock and send heartbeat
    clock.advance(25.0)
    resp = registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-01",
            host="127.0.0.2",
            port=6885,
            event=AnnounceEvent.HEARTBEAT,
        )
    )

    assert resp.interval == DEFAULT_HEARTBEAT_INTERVAL_SEC
    record = registry.get_peer(SAMPLE_SWARM_A, "peer-01")
    assert record is not None
    assert record.last_seen == 125.0
    assert record.host == "127.0.0.2"
    assert record.port == 6885
    assert record.is_seeder is True  # Preserved seeder status


def test_announce_heartbeat_for_unregistered_peer() -> None:
    # If tracker restarts, a heartbeat from an existing peer should re-register it
    clock = FakeClock(200.0)
    registry = SwarmRegistry(clock=clock)

    resp = registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-reconnected",
            host="10.0.0.1",
            port=6881,
            event=AnnounceEvent.HEARTBEAT,
            is_seeder=True,
        )
    )
    assert resp.interval == DEFAULT_HEARTBEAT_INTERVAL_SEC
    record = registry.get_peer(SAMPLE_SWARM_A, "peer-reconnected")
    assert record is not None
    assert record.last_seen == 200.0
    assert record.is_seeder is True


def test_announce_completed_marks_seeder() -> None:
    clock = FakeClock(10.0)
    registry = SwarmRegistry(clock=clock)

    # Start as leecher
    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-leecher",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
            is_seeder=False,
        )
    )
    record = registry.get_peer(SAMPLE_SWARM_A, "peer-leecher")
    assert record is not None
    assert record.is_seeder is False

    # Send completed event
    clock.advance(30.0)
    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-leecher",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.COMPLETED,
        )
    )

    record = registry.get_peer(SAMPLE_SWARM_A, "peer-leecher")
    assert record is not None
    assert record.is_seeder is True
    assert record.last_seen == 40.0

    clock.advance(5.0)
    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-leecher",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.COMPLETED,
        )
    )
    record = registry.get_peer(SAMPLE_SWARM_A, "peer-leecher")
    assert record is not None
    assert record.is_seeder is True
    assert record.last_seen == 45.0
    assert registry.peer_count(SAMPLE_SWARM_A) == 1


def test_announce_stopped_removes_peer_and_cleans_swarm() -> None:
    clock = FakeClock(10.0)
    registry = SwarmRegistry(clock=clock)

    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-01",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
        )
    )
    assert registry.peer_count(SAMPLE_SWARM_A) == 1
    assert SAMPLE_SWARM_A in registry.active_swarms()

    # Stopped announcement
    resp = registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-01",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STOPPED,
        )
    )
    assert resp.peers == []
    assert registry.get_peer(SAMPLE_SWARM_A, "peer-01") is None
    assert registry.peer_count(SAMPLE_SWARM_A) == 0
    # Cleaned up empty swarm
    assert SAMPLE_SWARM_A not in registry.active_swarms()


# ==============================================================================
# 4. Duplicate Announcements and Idempotency Tests
# ==============================================================================


def test_duplicate_started_announcements_are_idempotent() -> None:
    clock = FakeClock(10.0)
    registry = SwarmRegistry(clock=clock)

    req = AnnounceRequest(
        swarm_id=SAMPLE_SWARM_A,
        peer_id="peer-01",
        host="127.0.0.1",
        port=6881,
        event=AnnounceEvent.STARTED,
    )

    registry.announce(req)
    clock.advance(5.0)
    registry.announce(req)

    assert registry.peer_count(SAMPLE_SWARM_A) == 1
    record = registry.get_peer(SAMPLE_SWARM_A, "peer-01")
    assert record is not None
    assert record.last_seen == 15.0


def test_duplicate_stopped_announcements_are_idempotent() -> None:
    clock = FakeClock(10.0)
    registry = SwarmRegistry(clock=clock)

    stopped_req = AnnounceRequest(
        swarm_id=SAMPLE_SWARM_A,
        peer_id="nonexistent-peer",
        host="127.0.0.1",
        port=6881,
        event=AnnounceEvent.STOPPED,
    )

    # Calling stopped for a non-existent peer should succeed cleanly
    resp1 = registry.announce(stopped_req)
    resp2 = registry.announce(stopped_req)
    assert resp1.peers == []
    assert resp2.peers == []
    assert registry.peer_count(SAMPLE_SWARM_A) == 0


# ==============================================================================
# 5. Peer Self-Exclusion and Discovery Tests
# ==============================================================================


def test_caller_strictly_excluded_from_peers_list() -> None:
    registry = SwarmRegistry()

    # Peer 1 joins
    resp1 = registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-1",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
        )
    )
    assert resp1.peers == []

    # Peer 2 joins
    resp2 = registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-2",
            host="127.0.0.1",
            port=6882,
            event=AnnounceEvent.STARTED,
        )
    )
    assert len(resp2.peers) == 1
    assert resp2.peers[0].peer_id == "peer-1"
    assert resp2.peers[0].port == 6881

    # Peer 1 re-announces
    resp1_again = registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-1",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.HEARTBEAT,
        )
    )
    assert len(resp1_again.peers) == 1
    assert resp1_again.peers[0].peer_id == "peer-2"
    assert resp1_again.peers[0].port == 6882


def test_isolation_between_different_swarms() -> None:
    registry = SwarmRegistry()

    # Announce in Swarm A
    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-A1",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
        )
    )

    # Announce in Swarm B
    resp_b = registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_B,
            peer_id="peer-B1",
            host="127.0.0.1",
            port=6882,
            event=AnnounceEvent.STARTED,
        )
    )

    # Swarm B response must not see Peer-A1 from Swarm A
    assert resp_b.peers == []
    assert registry.peer_count(SAMPLE_SWARM_A) == 1
    assert registry.peer_count(SAMPLE_SWARM_B) == 1
    assert registry.peer_count() == 2


# ==============================================================================
# 6. Peer Limits and Sampling Tests
# ==============================================================================


def test_peer_limits_and_sampling() -> None:
    limit = 5
    rng = random.Random(42)  # Seeded RNG for reproducibility
    registry = SwarmRegistry(max_peers_per_announce=limit, rng=rng)

    # Register 10 peers in the swarm
    for i in range(10):
        registry.announce(
            AnnounceRequest(
                swarm_id=SAMPLE_SWARM_A,
                peer_id=f"peer-{i:02d}",
                host="127.0.0.1",
                port=6800 + i,
                event=AnnounceEvent.STARTED,
            )
        )

    assert registry.peer_count(SAMPLE_SWARM_A) == 10

    # Peer 11 announces and requests peer list
    resp = registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-caller",
            host="127.0.0.1",
            port=6999,
            event=AnnounceEvent.STARTED,
        )
    )

    assert len(resp.peers) == limit
    returned_peer_ids = [p.peer_id for p in resp.peers]
    assert "peer-caller" not in returned_peer_ids
    # Ensure no duplicates in sampled result
    assert len(set(returned_peer_ids)) == limit


def test_default_announce_peer_limit_is_50() -> None:
    registry = SwarmRegistry(rng=random.Random(42))
    for i in range(51):
        registry.announce(
            AnnounceRequest(
                swarm_id=SAMPLE_SWARM_A,
                peer_id=f"peer-{i:02d}",
                host="127.0.0.1",
                port=6800 + i,
                event=AnnounceEvent.STARTED,
            )
        )

    response = registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-caller",
            host="127.0.0.1",
            port=6999,
            event=AnnounceEvent.STARTED,
        )
    )

    assert len(response.peers) == 50
    assert "peer-caller" not in {peer.peer_id for peer in response.peers}


@pytest.mark.parametrize(
    ("configuration", "value"),
    [
        ("heartbeat_interval", 0),
        ("heartbeat_interval", -1),
        ("heartbeat_interval", True),
        ("heartbeat_interval", 1.5),
        ("expiry_multiplier", 0),
        ("expiry_multiplier", -1),
        ("expiry_multiplier", False),
        ("expiry_multiplier", 1.5),
        ("max_peers_per_announce", 0),
        ("max_peers_per_announce", -1),
        ("max_peers_per_announce", 51),
        ("max_peers_per_announce", True),
        ("max_peers_per_announce", 1.5),
    ],
)
def test_registry_rejects_invalid_configuration(configuration: str, value: object) -> None:
    with pytest.raises(ValueError):
        SwarmRegistry(**{configuration: value})  # type: ignore[arg-type]


# ==============================================================================
# 7. Stale Peer Eviction Tests with FakeClock
# ==============================================================================


def test_stale_peer_eviction_threshold() -> None:
    # 30s heartbeat * 3 multiplier = 90s expiry timeout
    clock = FakeClock(100.0)
    registry = SwarmRegistry(
        clock=clock,
        heartbeat_interval=30,
        expiry_multiplier=3,
    )
    assert registry.expiry_timeout == 90.0

    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-1",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
        )
    )

    # A peer exactly 90 seconds old is still active; expiry is strictly greater than 90.
    clock.advance(89.9)
    assert registry.evict_stale() == 0
    assert registry.get_peer(SAMPLE_SWARM_A, "peer-1") is not None
    clock.advance(0.1)
    assert registry.evict_stale() == 0
    assert registry.get_peer(SAMPLE_SWARM_A, "peer-1") is not None

    # Advance just past 90 seconds.
    clock.advance(0.2)
    evicted = registry.evict_stale()
    assert evicted == 1
    assert registry.get_peer(SAMPLE_SWARM_A, "peer-1") is None
    assert registry.peer_count(SAMPLE_SWARM_A) == 0
    assert SAMPLE_SWARM_A not in registry.active_swarms()


def test_swarm_listing_evicts_stale_peers_and_cleans_empty_swarm() -> None:
    clock = FakeClock(100.0)
    registry = SwarmRegistry(clock=clock)
    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-1",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
        )
    )

    clock.advance(90.0)
    assert len(registry.get_swarm_peers(SAMPLE_SWARM_A)) == 1
    clock.advance(0.1)
    assert registry.get_swarm_peers(SAMPLE_SWARM_A) == []
    assert SAMPLE_SWARM_A not in registry.active_swarms()


def test_announcement_triggers_lazy_eviction_of_stale_peers() -> None:
    clock = FakeClock(0.0)
    registry = SwarmRegistry(clock=clock, heartbeat_interval=10, expiry_multiplier=3)
    # Expiry threshold is 30.0 seconds

    # Peer 1 joins at t=0
    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-stale",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
        )
    )

    # Clock moves forward past expiry
    clock.advance(35.0)

    # Peer 2 joins; this announce call must lazily evict peer-stale
    resp = registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-new",
            host="127.0.0.1",
            port=6882,
            event=AnnounceEvent.STARTED,
        )
    )

    # peer-stale was evicted, so peer-new sees no peers
    assert resp.peers == []
    assert registry.get_peer(SAMPLE_SWARM_A, "peer-stale") is None
    assert registry.peer_count(SAMPLE_SWARM_A) == 1


def test_heartbeat_prevents_eviction() -> None:
    clock = FakeClock(0.0)
    registry = SwarmRegistry(clock=clock, heartbeat_interval=30, expiry_multiplier=3)
    # Expiry threshold = 90.0s

    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-active",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
        )
    )
    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-abandoned",
            host="127.0.0.1",
            port=6882,
            event=AnnounceEvent.STARTED,
        )
    )

    # At t=60, peer-active sends heartbeat
    clock.advance(60.0)
    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-active",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.HEARTBEAT,
        )
    )

    # At t=100: peer-abandoned hasn't announced for 100s (> 90s),
    # while peer-active announced at t=60 (elapsed 40s <= 90s).
    clock.advance(40.0)
    evicted = registry.evict_stale()

    assert evicted == 1
    assert registry.get_peer(SAMPLE_SWARM_A, "peer-abandoned") is None
    assert registry.get_peer(SAMPLE_SWARM_A, "peer-active") is not None


def test_targeted_swarm_eviction() -> None:
    clock = FakeClock(100.0)
    registry = SwarmRegistry(clock=clock, heartbeat_interval=30, expiry_multiplier=3)
    # Expiry threshold is 90s

    # Register peer in Swarm A at t=100
    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-A1",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
        )
    )
    # Register peer in Swarm B at t=100
    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_B,
            peer_id="peer-B1",
            host="127.0.0.1",
            port=6882,
            event=AnnounceEvent.STARTED,
        )
    )

    assert registry.peer_count(SAMPLE_SWARM_A) == 1
    assert registry.peer_count(SAMPLE_SWARM_B) == 1

    # Advance clock past expiry (elapsed 100s > 90s)
    clock.advance(100.0)

    # Evict ONLY Swarm A
    evicted_a = registry.evict_stale(swarm_id=SAMPLE_SWARM_A)
    assert evicted_a == 1
    assert registry.get_peer(SAMPLE_SWARM_A, "peer-A1") is None
    assert registry.peer_count(SAMPLE_SWARM_A) == 0

    # Swarm B must remain unaffected!
    assert registry.get_peer(SAMPLE_SWARM_B, "peer-B1") is not None
    assert registry.peer_count(SAMPLE_SWARM_B) == 1

    # Now evict Swarm B
    evicted_b = registry.evict_stale(swarm_id=SAMPLE_SWARM_B)
    assert evicted_b == 1
    assert registry.get_peer(SAMPLE_SWARM_B, "peer-B1") is None
    assert registry.peer_count(SAMPLE_SWARM_B) == 0
    assert registry.peer_count() == 0


# ==============================================================================
# 8. Empty and Unknown Swarm Queries
# ==============================================================================


def test_get_swarm_peers_unknown_and_populated() -> None:
    clock = FakeClock(10.0)
    registry = SwarmRegistry(clock=clock)

    # Unknown swarm returns empty list
    assert registry.get_swarm_peers("unknown-swarm-id") == []

    # Populate swarm
    registry.announce(
        AnnounceRequest(
            swarm_id=SAMPLE_SWARM_A,
            peer_id="peer-01",
            host="127.0.0.1",
            port=6881,
            event=AnnounceEvent.STARTED,
            is_seeder=True,
        )
    )

    peers = registry.get_swarm_peers(SAMPLE_SWARM_A)
    assert len(peers) == 1
    assert isinstance(peers[0], SwarmPeerInfo)
    assert peers[0].peer_id == "peer-01"
    assert peers[0].host == "127.0.0.1"
    assert peers[0].port == 6881
    assert peers[0].last_seen == 10.0
    assert peers[0].is_seeder is True
