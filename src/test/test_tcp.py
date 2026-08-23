"""Tests for vlan_probe.probe module: TCP probing."""

import socket

import pytest

from vlan_probe.probe import probe_target


def _tcp_listener() -> socket.socket:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    return server


def test_probe_tcp_unreachable() -> None:
    """An unreachable target that must be blocked passes."""
    target = {
        "name": "Unreachable Host",
        "vlan": "TestVLAN",
        "ip": "192.0.2.1",  # TEST-NET-1 (non-routable)
        "port": 80,
        "protocol": "tcp",
        "expected_blocked": True,
    }
    result = probe_target(target, timeout=1.0)
    assert result["status"] == "PASS"
    assert result["reachable"] is False


def test_probe_tcp_reachable_expected_open() -> None:
    """A TCP endpoint that accepts connections and must be reachable passes."""
    server = _tcp_listener()
    port = server.getsockname()[1]
    try:
        target = {
            "name": "Open Service",
            "vlan": "DMZ",
            "ip": "127.0.0.1",
            "port": port,
            "protocol": "tcp",
            "expected_blocked": False,
        }
        result = probe_target(target, timeout=2.0, local_ips=set())
        assert result["reachable"] is True
        assert result["status"] == "PASS"
        assert result["error"] is None
    finally:
        server.close()


def test_probe_tcp_reachable_expected_blocked() -> None:
    """Reaching a target that must be blocked is reported as a violation."""
    server = _tcp_listener()
    port = server.getsockname()[1]
    try:
        target = {
            "name": "Restricted Service",
            "vlan": "Internal",
            "ip": "127.0.0.1",
            "port": port,
            "protocol": "tcp",
            "expected_blocked": True,
        }
        result = probe_target(target, timeout=2.0, local_ips=set())
        assert result["reachable"] is True
        assert result["status"] == "FAIL"
        assert isinstance(result["error"], str)
        assert "UNAUTHORIZED_CONNECTIVITY_VIOLATION" in result["error"]
    finally:
        server.close()


def test_probe_tcp_closed_port_expected_open() -> None:
    """An unreachable endpoint that must be reachable fails with a clear error."""
    server = _tcp_listener()
    port = server.getsockname()[1]
    server.close()  # release the port so nothing listens on it
    target = {
        "name": "Required Service",
        "vlan": "Internet",
        "ip": "127.0.0.1",
        "port": port,
        "protocol": "tcp",
        "expected_blocked": False,
    }
    result = probe_target(target, timeout=1.0, local_ips=set())
    assert result["reachable"] is False
    assert result["status"] == "FAIL"
    assert isinstance(result["error"], str)
    assert "EXPECTED_CONNECTIVITY_FAILED" in result["error"]
    assert "Connection refused" in result["error"]


def test_probe_tcp_timeout_expected_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """A timed-out TCP connection reports Connection timed out in error details."""

    class TimedOutSocket:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def settimeout(self, timeout: float) -> None:
            pass

        def connect(self, addr: object) -> None:
            raise socket.timeout("timed out")

        def close(self) -> None:
            pass

    monkeypatch.setattr("vlan_probe.probe.socket.socket", TimedOutSocket)
    target = {
        "name": "Slow Service",
        "vlan": "Internet",
        "ip": "192.0.2.1",
        "port": 80,
        "protocol": "tcp",
        "expected_blocked": False,
    }
    result = probe_target(target, timeout=1.0, local_ips=set())
    assert result["reachable"] is False
    assert result["status"] == "FAIL"
    assert "Connection timed out" in str(result["error"])


def test_probe_tcp_oserror_expected_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """An OS error in TCP connect reports Socket error in error details."""

    class ErrorSocket:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def settimeout(self, timeout: float) -> None:
            pass

        def connect(self, addr: object) -> None:
            raise OSError("Network unreachable")

        def close(self) -> None:
            pass

    monkeypatch.setattr("vlan_probe.probe.socket.socket", ErrorSocket)
    target = {
        "name": "Unreachable Network",
        "vlan": "Internet",
        "ip": "192.0.2.1",
        "port": 80,
        "protocol": "tcp",
        "expected_blocked": False,
    }
    result = probe_target(target, timeout=1.0, local_ips=set())
    assert result["reachable"] is False
    assert result["status"] == "FAIL"
    assert "Socket error: Network unreachable" in str(result["error"])
