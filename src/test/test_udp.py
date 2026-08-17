"""Tests for vlan_probe.probe module: UDP probing."""

import socket
import threading
from typing import Any

import pytest

from vlan_probe.probe import probe_target


def _udp_echo_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    return sock


def _udp_echo_responder(sock: socket.socket) -> threading.Thread:
    def _respond() -> None:
        try:
            data, addr = sock.recvfrom(1024)
            sock.sendto(data, addr)
        except OSError:
            pass

    thread = threading.Thread(target=_respond)
    thread.start()
    return thread


def test_probe_udp_required_connectivity() -> None:
    """Probing an external UDP endpoint verifies the result structure."""
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


def test_probe_udp_dns_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A DNS probe sends a real DNS query packet to port 53."""
    created: list[Any] = []

    class FakeUDPSocket:
        def __init__(self, family: Any, socktype: Any) -> None:
            created.append(self)
            self.sent = b""

        def settimeout(self, timeout: float) -> None:
            pass

        def sendto(self, data: bytes, addr: Any) -> int:
            self.sent = data
            return len(data)

        def recvfrom(self, n: int) -> tuple[bytes, tuple[str, int]]:
            return b"dns-reply", ("127.0.0.1", 53)

        def close(self) -> None:
            pass

    monkeypatch.setattr("vlan_probe.probe.socket.socket", FakeUDPSocket)
    target = {
        "name": "DNS",
        "vlan": "External",
        "ip": "127.0.0.1",
        "port": 53,
        "protocol": "udp",
        "expected_blocked": False,
    }
    result = probe_target(target, timeout=2.0, local_ips=set())
    assert result["reachable"] is True
    assert result["status"] == "PASS"
    query = created[0].sent
    assert query[:2] == b"\x12\x34"  # DNS transaction ID
    assert b"example" in query  # the queried name


def test_probe_udp_other_port_reachable() -> None:
    """A UDP endpoint on a non-DNS port that responds is reachable."""
    sock = _udp_echo_socket()
    port = sock.getsockname()[1]
    assert port != 53
    thread = _udp_echo_responder(sock)
    try:
        target = {
            "name": "UDP Service",
            "vlan": "External",
            "ip": "127.0.0.1",
            "port": port,
            "protocol": "udp",
            "expected_blocked": False,
        }
        result = probe_target(target, timeout=2.0, local_ips=set())
        assert result["reachable"] is True
        assert result["status"] == "PASS"
    finally:
        thread.join(timeout=2.0)
        sock.close()


def test_probe_udp_silent_endpoint_times_out() -> None:
    """A UDP endpoint that never responds is unreachable (timeout)."""
    sock = _udp_echo_socket()  # bound but never responds
    port = sock.getsockname()[1]
    try:
        target = {
            "name": "Silent UDP",
            "vlan": "Internal",
            "ip": "127.0.0.1",
            "port": port,
            "protocol": "udp",
            "expected_blocked": True,
        }
        result = probe_target(target, timeout=0.5, local_ips=set())
        assert result["reachable"] is False
        assert result["status"] == "PASS"
    finally:
        sock.close()


def test_probe_udp_closed_port() -> None:
    """UDP to a closed port surfaces as an error and is unreachable."""
    sock = _udp_echo_socket()
    port = sock.getsockname()[1]
    sock.close()  # release the port so nothing responds
    target = {
        "name": "Closed UDP",
        "vlan": "Internal",
        "ip": "127.0.0.1",
        "port": port,
        "protocol": "udp",
        "expected_blocked": True,
    }
    result = probe_target(target, timeout=1.0, local_ips=set())
    assert result["reachable"] is False
    assert result["status"] == "PASS"


def test_probe_udp_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-timeout UDP error (e.g. connection reset) is treated as unreachable."""

    class FailingUDPSocket:
        def __init__(self, family: Any, socktype: Any) -> None:
            pass

        def settimeout(self, timeout: float) -> None:
            pass

        def sendto(self, data: bytes, addr: Any) -> int:
            return 0

        def recvfrom(self, n: int) -> tuple[bytes, tuple[str, int]]:
            raise ConnectionResetError("connection reset by peer")

        def close(self) -> None:
            pass

    monkeypatch.setattr("vlan_probe.probe.socket.socket", FailingUDPSocket)
    target = {
        "name": "Resetting UDP",
        "vlan": "Internal",
        "ip": "10.0.0.1",
        "port": 1234,
        "protocol": "udp",
        "expected_blocked": True,
    }
    result = probe_target(target, timeout=1.0, local_ips=set())
    assert result["reachable"] is False
    assert result["status"] == "PASS"
