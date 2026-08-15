"""Tests for vlan_probe.config module."""

import pytest

from vlan_probe.config import MQTTConfig, load_config, parse_mqtt_config


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
