"""Tests for vlan_probe.probe module: SCTP probing."""

import socket

import pytest

from vlan_probe.probe import probe_target


def _sctp_proto() -> int:
    return getattr(socket, "IPPROTO_SCTP", 132)


def _target(**overrides) -> dict:
    target = {
        "name": "SCTP Target",
        "vlan": "Internal",
        "ip": "10.0.0.1",
        "port": 3868,
        "protocol": "sctp",
        "expected_blocked": True,
    }
    target.update(overrides)
    return target


def test_probe_sctp_reachable(monkeypatch):
    """SCTP uses a one-to-one socket with the SCTP protocol; a successful association is reachable."""
    created = []

    class FakeSCTPSocket:
        def __init__(self, family, socktype, proto):
            created.append(self)
            self.socktype = socktype
            self.proto = proto
            self.closed = False

        def settimeout(self, timeout):
            pass

        def connect(self, addr):
            pass

        def close(self):
            self.closed = True

    monkeypatch.setattr("vlan_probe.probe.socket.socket", FakeSCTPSocket)
    result = probe_target(_target(expected_blocked=False), timeout=1.0, local_ips=set())
    assert result["reachable"] is True
    assert result["status"] == "PASS"
    assert created[0].socktype == socket.SOCK_STREAM
    assert created[0].proto == _sctp_proto()
    assert created[0].closed is True


def test_probe_sctp_unreachable(monkeypatch):
    """A refused SCTP association is unreachable."""

    class RefusedSocket:
        def __init__(self, family, socktype, proto):
            pass

        def settimeout(self, timeout):
            pass

        def connect(self, addr):
            raise ConnectionRefusedError("refused")

        def close(self):
            pass

    monkeypatch.setattr("vlan_probe.probe.socket.socket", RefusedSocket)
    result = probe_target(_target(), timeout=1.0, local_ips=set())
    assert result["reachable"] is False
    assert result["status"] == "PASS"


def test_probe_sctp_timeout(monkeypatch):
    """A timed-out SCTP association is unreachable."""

    class TimedOutSocket:
        def __init__(self, family, socktype, proto):
            pass

        def settimeout(self, timeout):
            pass

        def connect(self, addr):
            raise socket.timeout("timed out")

        def close(self):
            pass

    monkeypatch.setattr("vlan_probe.probe.socket.socket", TimedOutSocket)
    result = probe_target(_target(), timeout=1.0, local_ips=set())
    assert result["reachable"] is False
    assert result["status"] == "PASS"


def test_probe_sctp_not_supported(monkeypatch):
    """A host without SCTP support reports the target as unreachable."""
    monkeypatch.setattr(
        "vlan_probe.probe.socket.socket",
        lambda *a, **k: (_ for _ in ()).throw(OSError(93, "Protocol not supported")),
    )
    result = probe_target(_target(), timeout=1.0, local_ips=set())
    assert result["reachable"] is False
    assert result["status"] == "PASS"


def _sctp_available() -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, _sctp_proto())
        sock.close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _sctp_available(), reason="SCTP not available on this host")
def test_probe_sctp_real_loopback():
    """A real SCTP association with a loopback listener is reachable."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM, _sctp_proto())
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        target = _target(ip="127.0.0.1", port=port, expected_blocked=False)
        result = probe_target(target, timeout=2.0, local_ips=set())
        assert result["reachable"] is True
        assert result["status"] == "PASS"
    finally:
        server.close()
