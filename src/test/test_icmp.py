"""Tests for vlan_probe.probe module: ICMP (ping) probing."""

import shutil
import subprocess
from typing import Any

import pytest

from vlan_probe.probe import probe_target


def _target(**overrides: Any) -> dict[str, Any]:
    target: dict[str, Any] = {
        "name": "Ping Target",
        "vlan": "Internal",
        "ip": "10.0.0.1",
        "port": 0,
        "protocol": "icmp",
        "expected_blocked": True,
    }
    target.update(overrides)
    return target


def _fake_run(returncode: int) -> Any:
    def fake_run(*args: Any, **kwargs: Any) -> Any:
        return type("Completed", (), {"returncode": returncode})()

    return fake_run


def test_probe_icmp_builds_ping_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ping subprocess is invoked with a single probe and bounded timeout."""
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> Any:
        captured["args"] = args[0]
        captured["timeout"] = kwargs.get("timeout")
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr("vlan_probe.probe.subprocess.run", fake_run)
    result = probe_target(_target(ip="10.0.0.1", expected_blocked=False), timeout=2.0, local_ips=set())
    assert captured["args"] == ["ping", "-c", "1", "-W", "2.0", "10.0.0.1"]
    assert captured["timeout"] == 3.0
    assert result["reachable"] is True
    assert result["status"] == "PASS"


def test_probe_icmp_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-zero ping exit code means the target is unreachable."""
    monkeypatch.setattr("vlan_probe.probe.subprocess.run", _fake_run(returncode=1))
    result = probe_target(_target(), timeout=1.0, local_ips=set())
    assert result["reachable"] is False
    assert result["status"] == "PASS"


def test_probe_icmp_reachable_expected_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """A reachable ping to a target that must be blocked is a violation."""
    monkeypatch.setattr("vlan_probe.probe.subprocess.run", _fake_run(returncode=0))
    result = probe_target(_target(), timeout=1.0, local_ips=set())
    assert result["reachable"] is True
    assert result["status"] == "FAIL"
    assert "UNAUTHORIZED_CONNECTIVITY_VIOLATION" in result["error"]


def test_probe_icmp_ping_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing ping binary is treated as unreachable."""
    monkeypatch.setattr(
        "vlan_probe.probe.subprocess.run",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("ping not found")),
    )
    result = probe_target(_target(), timeout=1.0, local_ips=set())
    assert result["reachable"] is False
    assert result["status"] == "PASS"


def test_probe_icmp_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ping that exceeds the timeout is treated as unreachable."""
    monkeypatch.setattr(
        "vlan_probe.probe.subprocess.run",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("ping", 2.0)),
    )
    result = probe_target(_target(), timeout=2.0, local_ips=set())
    assert result["reachable"] is False
    assert result["status"] == "PASS"


@pytest.mark.skipif(shutil.which("ping") is None, reason="ping binary not available")
def test_probe_icmp_real_loopback() -> None:
    """Pinging the loopback interface is reported as reachable."""
    target = _target(ip="127.0.0.1", expected_blocked=False)
    result = probe_target(target, timeout=2.0, local_ips=set())
    assert result["reachable"] is True
    assert result["status"] == "PASS"
