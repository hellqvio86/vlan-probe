"""Tests for vlan_probe.config module."""

import pytest

from vlan_probe.config import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_FORMAT,
    DEFAULT_TIMEOUT,
    MQTTConfig,
    default_config_path,
    default_format,
    default_strict,
    default_timeout,
    load_config,
    parse_mqtt_config,
)


def test_parse_mqtt_config_defaults():
    cfg = parse_mqtt_config({"host": "mqtt.example.com"})
    assert cfg.host == "mqtt.example.com"
    assert cfg.port == 1883
    assert cfg.topic_prefix == "vlan-probe"
    assert cfg.retain is True
    assert cfg.qos == 1
    assert cfg.connect_timeout == 5.0


def test_parse_mqtt_config_full():
    cfg = parse_mqtt_config(
        {
            "host": "mqtt.example.com",
            "port": 8883,
            "username": "user",
            "password": "pw",
            "tls": True,
            "topic_prefix": "net",
            "retain": False,
            "qos": 0,
            "connect_timeout": 2.5,
        }
    )
    assert cfg == MQTTConfig(
        host="mqtt.example.com",
        port=8883,
        username="user",
        password="pw",
        tls=True,
        topic_prefix="net",
        retain=False,
        qos=0,
        connect_timeout=2.5,
    )


@pytest.mark.parametrize(
    "section",
    [
        {},
        {"host": 123},
        {"host": "h", "port": 0},
        {"host": "h", "port": 70000},
        {"host": "h", "qos": 3},
        {"host": "h", "connect_timeout": -1},
        {"host": ""},
        {"host": "h", "topic_prefix": ""},
        {"host": "h", "ca_certs": 123},
        "not a table",
        ["not", "a", "table"],
    ],
)
def test_parse_mqtt_config_invalid(section):
    with pytest.raises(SystemExit) as excinfo:
        parse_mqtt_config(section)
    assert excinfo.value.code == 2


def test_load_config_with_mqtt(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[[targets]]\nname = "A"\nvlan = "Internal"\nip = "10.0.0.1"\nport = 22\n'
        'protocol = "tcp"\nexpected_blocked = true\n\n[mqtt]\nhost = "broker.local"\n'
    )
    cfg = load_config(str(config_file))
    assert len(cfg.targets) == 1
    assert cfg.targets[0]["name"] == "A"
    assert cfg.mqtt is not None
    assert cfg.mqtt.host == "broker.local"


def test_load_config_without_mqtt(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[[targets]]\nname = "A"\nvlan = "V"\nip = "10.0.0.1"\nport = 1\nprotocol = "tcp"\n')
    cfg = load_config(str(config_file))
    assert cfg.mqtt is None


def test_load_config_missing_file(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        load_config(str(tmp_path / "nope.toml"))
    assert excinfo.value.code == 2


def test_load_config_invalid_json(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text("{ this is not valid json")
    with pytest.raises(SystemExit) as excinfo:
        load_config(str(config_file))
    assert excinfo.value.code == 2


def test_load_config_json_list(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text('[{"name": "A", "vlan": "V", "ip": "10.0.0.1", "port": 22}]')
    cfg = load_config(str(config_file))
    assert len(cfg.targets) == 1
    assert cfg.targets[0]["name"] == "A"
    assert cfg.mqtt is None


def test_load_config_targets_not_a_list(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"targets": "not a list"}')
    with pytest.raises(SystemExit) as excinfo:
        load_config(str(config_file))
    assert excinfo.value.code == 2


def test_load_config_no_tomli(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("vlan_probe.config.tomllib", None)
    config_file = tmp_path / "config.toml"
    config_file.write_text("")
    with pytest.raises(SystemExit) as excinfo:
        load_config(str(config_file))
    assert excinfo.value.code == 2
    assert "tomli" in capsys.readouterr().err


def test_default_config_path(monkeypatch):
    monkeypatch.delenv("VLAN_PROBE_CONFIG", raising=False)
    assert default_config_path() == DEFAULT_CONFIG_PATH
    monkeypatch.setenv("VLAN_PROBE_CONFIG", "/tmp/custom.toml")
    assert default_config_path() == "/tmp/custom.toml"


def test_default_timeout(monkeypatch):
    monkeypatch.delenv("VLAN_PROBE_TIMEOUT", raising=False)
    assert default_timeout() == DEFAULT_TIMEOUT
    monkeypatch.setenv("VLAN_PROBE_TIMEOUT", "5.5")
    assert default_timeout() == 5.5


@pytest.mark.parametrize("value", ["abc", "0", "-1"])
def test_default_timeout_invalid(monkeypatch, value):
    monkeypatch.setenv("VLAN_PROBE_TIMEOUT", value)
    with pytest.raises(SystemExit) as excinfo:
        default_timeout()
    assert excinfo.value.code == 2


def test_default_format(monkeypatch):
    monkeypatch.delenv("VLAN_PROBE_FORMAT", raising=False)
    assert default_format() == DEFAULT_FORMAT
    monkeypatch.setenv("VLAN_PROBE_FORMAT", "table")
    assert default_format() == "table"


def test_default_format_invalid(monkeypatch):
    monkeypatch.setenv("VLAN_PROBE_FORMAT", "yaml")
    with pytest.raises(SystemExit) as excinfo:
        default_format()
    assert excinfo.value.code == 2


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("YES", True),
        ("on", True),
        ("0", False),
        ("no", False),
        ("off", False),
        ("", False),
    ],
)
def test_default_strict(monkeypatch, value, expected):
    monkeypatch.setenv("VLAN_PROBE_STRICT", value)
    assert default_strict() is expected


def test_default_strict_unset(monkeypatch):
    monkeypatch.delenv("VLAN_PROBE_STRICT", raising=False)
    assert default_strict() is False


def test_parse_mqtt_config_with_env_overrides():
    overrides = {
        "host": "env.broker",
        "port": 8883,
        "username": "envuser",
        "password": "envpw",
        "tls": True,
        "ca_certs": "/certs/ca.pem",
        "insecure": True,
        "topic_prefix": "env-prefix",
        "retain": False,
        "qos": 2,
        "connect_timeout": 3.5,
    }
    cfg = parse_mqtt_config({"host": "file.broker", "port": 1883}, overrides)
    assert cfg == MQTTConfig(
        host="env.broker",
        port=8883,
        username="envuser",
        password="envpw",
        tls=True,
        ca_certs="/certs/ca.pem",
        insecure=True,
        topic_prefix="env-prefix",
        retain=False,
        qos=2,
        connect_timeout=3.5,
    )


def test_parse_mqtt_config_env_bools():
    cfg = parse_mqtt_config({}, {"host": "h", "tls": "on", "insecure": "yes", "retain": "off"})
    assert cfg.tls is True
    assert cfg.insecure is True
    assert cfg.retain is False


def test_load_config_mqtt_from_env_only(tmp_path, monkeypatch):
    monkeypatch.setenv("VLAN_PROBE_MQTT_HOST", "env.broker")
    monkeypatch.setenv("VLAN_PROBE_MQTT_PORT", "8883")
    monkeypatch.setenv("VLAN_PROBE_MQTT_USERNAME", "envuser")
    monkeypatch.setenv("VLAN_PROBE_MQTT_PASSWORD", "envpw")
    monkeypatch.setenv("VLAN_PROBE_MQTT_TLS", "1")
    monkeypatch.setenv("VLAN_PROBE_MQTT_CA_CERTS", "/certs/ca.pem")
    monkeypatch.setenv("VLAN_PROBE_MQTT_INSECURE", "yes")
    monkeypatch.setenv("VLAN_PROBE_MQTT_TOPIC_PREFIX", "env-prefix")
    monkeypatch.setenv("VLAN_PROBE_MQTT_RETAIN", "0")
    monkeypatch.setenv("VLAN_PROBE_MQTT_QOS", "2")
    monkeypatch.setenv("VLAN_PROBE_MQTT_CONNECT_TIMEOUT", "2.5")
    config_file = tmp_path / "config.toml"
    config_file.write_text('[[targets]]\nname = "A"\nvlan = "V"\nip = "10.0.0.1"\nport = 1\nprotocol = "tcp"\n')
    cfg = load_config(str(config_file))
    assert cfg.mqtt == MQTTConfig(
        host="env.broker",
        port=8883,
        username="envuser",
        password="envpw",
        tls=True,
        ca_certs="/certs/ca.pem",
        insecure=True,
        topic_prefix="env-prefix",
        retain=False,
        qos=2,
        connect_timeout=2.5,
    )


def test_load_config_mqtt_env_overrides_section(tmp_path, monkeypatch):
    monkeypatch.setenv("VLAN_PROBE_MQTT_HOST", "env.broker")
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[[targets]]\nname = "A"\nvlan = "V"\nip = "10.0.0.1"\nport = 1\nprotocol = "tcp"\n'
        '\n[mqtt]\nhost = "file.broker"\n'
    )
    cfg = load_config(str(config_file))
    assert cfg.mqtt is not None
    assert cfg.mqtt.host == "env.broker"
    assert cfg.mqtt.port == 1883


@pytest.mark.parametrize(
    ("var", "value"),
    [
        ("VLAN_PROBE_MQTT_PORT", "not-a-port"),
        ("VLAN_PROBE_MQTT_QOS", "x"),
        ("VLAN_PROBE_MQTT_CONNECT_TIMEOUT", "slow"),
    ],
)
def test_load_config_invalid_mqtt_env(tmp_path, monkeypatch, var, value):
    monkeypatch.setenv(var, value)
    config_file = tmp_path / "config.toml"
    config_file.write_text('[[targets]]\nname = "A"\nvlan = "V"\nip = "10.0.0.1"\nport = 1\nprotocol = "tcp"\n')
    with pytest.raises(SystemExit) as excinfo:
        load_config(str(config_file))
    assert excinfo.value.code == 2
