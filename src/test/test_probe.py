"""Tests for vlan_probe.probe module: core probe behavior."""

from typing import Any

import pytest

from vlan_probe.probe import get_local_ips, probe_target


def test_get_local_ips() -> None:
    """Test that get_local_ips returns a set containing at least 127.0.0.1."""
    ips = get_local_ips()
    assert isinstance(ips, set)
    assert "127.0.0.1" in ips


def test_get_local_ips_ip_command_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fall back to hostname resolution when the ``ip`` binary is unavailable."""

    def raise_missing(*args: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError("ip command not found")

    monkeypatch.setattr("vlan_probe.probe.subprocess.check_output", raise_missing)
    ips = get_local_ips()
    assert isinstance(ips, set)
    assert "127.0.0.1" in ips


def test_get_local_ips_hostname_resolution_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both fallback mechanisms failing yields loopback addresses."""

    def raise_missing(*args: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError("ip command not found")

    def raise_socket_error(*args: Any, **kwargs: Any) -> Any:
        raise OSError("no hostname")

    monkeypatch.setattr("vlan_probe.probe.subprocess.check_output", raise_missing)
    monkeypatch.setattr("vlan_probe.probe.socket.gethostbyname_ex", raise_socket_error)
    assert get_local_ips() == {"127.0.0.1", "::1"}


def test_get_local_ips_parses_ipv4_and_ipv6(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ip command output parses both IPv4 and IPv6 addresses with prefixes and scopes."""
    fake_ip_output = (
        "1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever preferred_lft forever\n"
        "1: lo    inet6 ::1/128 scope host \\       valid_lft forever preferred_lft forever\n"
        "2: eth0    inet 192.168.1.50/24 brd 192.168.1.255 scope global eth0\n"
        "2: eth0    inet6 fe80::1ff:fe00:1%eth0/64 scope link \n"
    )
    monkeypatch.setattr("vlan_probe.probe.subprocess.check_output", lambda *a, **k: fake_ip_output)
    ips = get_local_ips()
    assert "127.0.0.1" in ips
    assert "::1" in ips
    assert "192.168.1.50" in ips
    assert "fe80::1ff:fe00:1" in ips


def test_probe_target_localhost() -> None:
    """Test probing localhost (should pass as exempt self-host with status SKIP)."""
    target = {
        "name": "Test Localhost",
        "vlan": "Test",
        "ip": "127.0.0.1",
        "port": 22,
        "protocol": "tcp",
        "expected_blocked": True,
    }
    result = probe_target(target, timeout=1.0)

    assert result["status"] == "SKIP"
    assert isinstance(result["error"], str)
    assert "EXEMPT_SELF_HOST" in result["error"]
    assert result["target_name"] == "Test Localhost"
    assert result["target_vlan"] == "Test"


def test_probe_port_as_string() -> None:
    """Ports given as strings are coerced to integers."""
    target: dict[str, Any] = {
        "name": "String Port",
        "vlan": "Internal",
        "ip": "192.0.2.1",
        "port": "80",
        "protocol": "tcp",
        "expected_blocked": True,
    }
    result = probe_target(target, timeout=0.5, local_ips=set())
    assert result["port"] == 80


def test_probe_target_defaults() -> None:
    """Missing keys fall back to sensible defaults."""
    target: dict[str, Any] = {"ip": "192.0.2.1"}
    result = probe_target(target, timeout=0.5, local_ips=set())
    assert result["target_name"] == "Unknown Target"
    assert result["target_vlan"] == "Unknown VLAN"
    assert result["port"] == 80
    assert result["protocol"] == "tcp"
    assert result["expected_blocked"] is True
    assert result["reachable"] is False


def test_probe_target_unknown_protocol() -> None:
    """Unknown protocol is treated as unreachable."""
    target: dict[str, Any] = {
        "name": "Unknown Proto",
        "vlan": "Internal",
        "ip": "192.0.2.1",
        "port": 80,
        "protocol": "custom_proto",
        "expected_blocked": True,
    }
    result = probe_target(target, timeout=0.5, local_ips=set())
    assert result["reachable"] is False
    assert result["status"] == "PASS"
