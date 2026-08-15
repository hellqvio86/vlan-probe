"""Tests for vlan_probe.probe module."""

from vlan_probe.probe import get_local_ips, probe_target


def test_get_local_ips():
    """Test that get_local_ips returns a set containing at least 127.0.0.1."""
    ips = get_local_ips()
    assert isinstance(ips, set)
    assert "127.0.0.1" in ips


def test_probe_target_localhost():
    """Test probing localhost (should pass as exempt self-host)."""
    target = {
        "name": "Test Localhost",
        "vlan": "Test",
        "ip": "127.0.0.1",
        "port": 22,
        "protocol": "tcp",
        "expected_blocked": True,
    }
    result = probe_target(target, timeout=1.0)

    assert result["status"] == "PASS"
    assert "EXEMPT_SELF_HOST" in result["error"]
    assert result["target_name"] == "Test Localhost"
    assert result["target_vlan"] == "Test"


def test_probe_target_unreachable():
    """Test probing an unreachable host (should fail since it's expected_blocked=True)."""
    target = {
        "name": "Unreachable Host",
        "vlan": "TestVLAN",
        "ip": "192.0.2.1",  # TEST-NET-1 (non-routable)
        "port": 80,
        "protocol": "tcp",
        "expected_blocked": True,
    }
    result = probe_target(target, timeout=1.0)

    # Should pass because the target is unreachable (expected_blocked=True means connection should fail)
    assert result["status"] == "PASS"
    assert result["reachable"] is False


def test_probe_target_required_connectivity():
    """Test probing a target with expected_blocked=False."""
    target = {
        "name": "Required Service",
        "vlan": "Internet",
        "ip": "1.1.1.1",  # Cloudflare DNS
        "port": 53,
        "protocol": "udp",
        "expected_blocked": False,
    }
    result = probe_target(target, timeout=2.0)

    # We can't guarantee this will succeed in all environments,
    # so we just verify the structure is correct
    assert result["status"] in ["PASS", "FAIL"]
    assert result["target_ip"] == "1.1.1.1"
    assert result["port"] == 53
    assert result["protocol"] == "udp"
    assert result["expected_blocked"] is False
