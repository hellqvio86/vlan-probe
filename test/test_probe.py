"""Tests for vlan_probe.probe module."""

import socket
import threading

from vlan_probe.probe import get_local_ips, probe_target


def _tcp_listener() -> "socket.socket":
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    return server


def _udp_echo_socket() -> "socket.socket":
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    return sock


def _udp_echo_responder(sock: "socket.socket") -> threading.Thread:
    def _respond() -> None:
        try:
            data, addr = sock.recvfrom(1024)
            sock.sendto(data, addr)
        except OSError:
            pass

    thread = threading.Thread(target=_respond)
    thread.start()
    return thread


def test_get_local_ips():
    """Test that get_local_ips returns a set containing at least 127.0.0.1."""
    ips = get_local_ips()
    assert isinstance(ips, set)
    assert "127.0.0.1" in ips


def test_get_local_ips_ip_command_missing(monkeypatch):
    """Fall back to hostname resolution when the ``ip`` binary is unavailable."""

    def raise_missing(*args, **kwargs):
        raise FileNotFoundError("ip command not found")

    monkeypatch.setattr("vlan_probe.probe.subprocess.check_output", raise_missing)
    ips = get_local_ips()
    assert isinstance(ips, set)
    assert "127.0.0.1" in ips


def test_get_local_ips_hostname_resolution_fails(monkeypatch):
    """Both fallback mechanisms failing yields only the loopback address."""

    def raise_missing(*args, **kwargs):
        raise FileNotFoundError("ip command not found")

    def raise_socket_error(*args, **kwargs):
        raise OSError("no hostname")

    monkeypatch.setattr("vlan_probe.probe.subprocess.check_output", raise_missing)
    monkeypatch.setattr("vlan_probe.probe.socket.gethostbyname_ex", raise_socket_error)
    assert get_local_ips() == {"127.0.0.1"}


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


def test_probe_tcp_reachable_expected_open():
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


def test_probe_tcp_reachable_expected_blocked():
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
        assert "UNAUTHORIZED_CONNECTIVITY_VIOLATION" in result["error"]
    finally:
        server.close()


def test_probe_tcp_closed_port_expected_open():
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
    assert "EXPECTED_CONNECTIVITY_FAILED" in result["error"]


def test_probe_udp_dns_reachable(monkeypatch):
    """A DNS probe sends a real DNS query packet to port 53."""
    created: list = []

    class FakeUDPSocket:
        def __init__(self, family, socktype):
            created.append(self)
            self.sent = b""

        def settimeout(self, timeout):
            pass

        def sendto(self, data, addr):
            self.sent = data

        def recvfrom(self, n):
            return b"dns-reply", ("127.0.0.1", 53)

        def close(self):
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


def test_probe_udp_other_port_reachable():
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


def test_probe_udp_silent_endpoint_times_out():
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


def test_probe_udp_closed_port():
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


def test_probe_udp_generic_error(monkeypatch):
    """A non-timeout UDP error (e.g. connection reset) is treated as unreachable."""

    class FailingUDPSocket:
        def __init__(self, family, socktype):
            pass

        def settimeout(self, timeout):
            pass

        def sendto(self, data, addr):
            pass

        def recvfrom(self, n):
            raise ConnectionResetError("connection reset by peer")

        def close(self):
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


def test_probe_port_as_string():
    """Ports given as strings are coerced to integers."""
    target = {
        "name": "String Port",
        "vlan": "Internal",
        "ip": "192.0.2.1",
        "port": "80",
        "protocol": "tcp",
        "expected_blocked": True,
    }
    result = probe_target(target, timeout=0.5, local_ips=set())
    assert result["port"] == 80


def test_probe_target_defaults():
    """Missing keys fall back to sensible defaults."""
    target = {"ip": "192.0.2.1"}
    result = probe_target(target, timeout=0.5, local_ips=set())
    assert result["target_name"] == "Unknown Target"
    assert result["target_vlan"] == "Unknown VLAN"
    assert result["port"] == 80
    assert result["protocol"] == "tcp"
    assert result["expected_blocked"] is True
    assert result["reachable"] is False
