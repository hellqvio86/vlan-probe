"""Tests for vlan_probe.mqtt_report module."""

import json
from typing import List, Optional, Tuple

import pytest

from vlan_probe.config import MQTTConfig
from vlan_probe.mqtt_report import (
    MQTTPublishError,
    build_messages,
    build_topic_prefix,
    publish_to_mqtt,
    slugify,
)


class FakeInfo:
    def __init__(self, fail: bool = False):
        self._fail = fail

    def wait_for_publish(self, timeout: Optional[float] = None) -> None:
        if self._fail:
            raise RuntimeError("broker ack timeout")


class FakeClient:
    def __init__(self):
        self.published: List[Tuple[str, str, int, bool]] = []
        self.connected = False
        self.disconnected = False
        self.loops_started = 0
        self.loops_stopped = 0
        self.tls_configured = False
        self.tls_insecure = False
        self.credentials: Optional[Tuple[str, Optional[str]]] = None
        self.connect_error: Optional[Exception] = None
        self.publish_error = False

    def tls_set(self, ca_certs=None):
        self.tls_configured = True

    def tls_insecure_set(self, value):
        self.tls_insecure = bool(value)

    def username_pw_set(self, username, password=None):
        self.credentials = (username, password)

    def connect(self, host, port, keepalive=60, **kwargs):
        if self.connect_error:
            raise self.connect_error
        self.connected = True
        self.connect_args = (host, port, keepalive, kwargs)

    def loop_start(self):
        self.loops_started += 1

    def loop_stop(self):
        self.loops_stopped += 1

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))
        return FakeInfo(fail=self.publish_error)

    def disconnect(self):
        self.disconnected = True


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr("vlan_probe.mqtt_report.mqtt.Client", lambda *a, **k: client)
    return client


def _cfg(**kwargs) -> MQTTConfig:
    defaults = dict(host="mqtt.example.com")
    defaults.update(kwargs)
    return MQTTConfig(**defaults)


def test_slugify():
    assert slugify("Internal - Device A SSH") == "internal-device-a-ssh"
    assert slugify("  Guest  VLAN  ") == "guest-vlan"
    assert slugify("DMZ.Web.Server") == "dmz-web-server"
    assert slugify("") == "target"
    assert slugify("🦄") == "target"
    assert slugify("MixedCaseName") == "mixedcasename"


def test_build_topic_prefix():
    assert build_topic_prefix("vlan-probe", "my-host") == "vlan-probe/my-host"
    assert build_topic_prefix("prefix", "Host With Spaces") == "prefix/host-with-spaces"


def test_build_messages_layout():
    results = [
        {"target_name": "Device A", "target_vlan": "Internal", "status": "PASS"},
        {"target_name": "Web Server", "target_vlan": "DMZ", "status": "FAIL"},
    ]
    summary = {"total_probed": 2, "passed": 1, "failed": 1, "violations": []}
    messages = build_messages(results, summary, _cfg(), hostname="host1")

    topics = [t for t, _ in messages]
    assert topics[0] == "vlan-probe/host1/summary"
    assert "vlan-probe/host1/targets/internal/device-a" in topics
    assert "vlan-probe/host1/targets/dmz/web-server" in topics
    assert len(messages) == 3
    assert json.loads(messages[0][1]) == summary
    assert json.loads(messages[1][1]) == results[0]


def test_build_messages_collision():
    results = [
        {"target_name": "Device A", "target_vlan": "Internal", "status": "PASS"},
        {"target_name": "Device.A", "target_vlan": "Internal", "status": "PASS"},
    ]
    messages = build_messages(results, {"total_probed": 2}, _cfg(), hostname="host1")
    topics = [t for t, _ in messages]
    assert len(topics) == 3
    assert len(set(topics)) == 3
    suffix_seen = [t for t in topics if len(t.rsplit("-", 1)[-1]) == 8]
    assert len(suffix_seen) == 1
    assert suffix_seen[0].startswith("vlan-probe/host1/targets/internal/device-a-")


def test_publish_success(fake_client):
    cfg = _cfg(qos=1, retain=True)
    messages = [("a/summary", "{}"), ("a/targets/x/y", "{}")]
    publish_to_mqtt(cfg, messages)

    assert fake_client.connected
    assert fake_client.disconnected
    assert fake_client.loops_started == 1
    assert fake_client.loops_stopped == 1
    assert fake_client.published == [
        ("a/summary", "{}", 1, True),
        ("a/targets/x/y", "{}", 1, True),
    ]
    assert fake_client.connect_args[0] == "mqtt.example.com"


def test_publish_with_auth_tls(fake_client):
    cfg = _cfg(username="user", password="pw", tls=True, insecure=True)
    publish_to_mqtt(cfg, [("a/summary", "{}")])

    assert fake_client.tls_configured
    assert fake_client.tls_insecure
    assert fake_client.credentials == ("user", "pw")


def test_publish_connect_failure(fake_client):
    fake_client.connect_error = ConnectionRefusedError("nope")
    with pytest.raises(MQTTPublishError):
        publish_to_mqtt(_cfg(), [("a/summary", "{}")])
    assert not fake_client.connected


def test_publish_delivery_failure(fake_client):
    fake_client.publish_error = True
    with pytest.raises(MQTTPublishError):
        publish_to_mqtt(_cfg(), [("a/summary", "{}")])
    assert fake_client.disconnected
