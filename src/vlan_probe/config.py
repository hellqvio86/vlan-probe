"""Configuration loading for vlan_probe."""

import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # Fallback for Python < 3.11
    except ImportError:
        tomllib = None

DEFAULT_CONFIG_PATH = "/etc/vlan_probe.toml"

DEFAULT_MQTT_PORT = 1883
DEFAULT_TOPIC_PREFIX = "vlan-probe"


@dataclass
class MQTTConfig:
    """MQTT broker connection and delivery settings."""

    host: str
    port: int = DEFAULT_MQTT_PORT
    username: Optional[str] = None
    password: Optional[str] = None
    tls: bool = False
    ca_certs: Optional[str] = None
    insecure: bool = False
    topic_prefix: str = DEFAULT_TOPIC_PREFIX
    retain: bool = True
    qos: int = 1
    connect_timeout: float = 5.0


@dataclass
class Config:
    """Full vlan_probe configuration."""

    targets: List[Dict[str, Any]]
    mqtt: Optional[MQTTConfig] = None


def _fail(message: str) -> None:
    sys.stderr.write(f"Error: {message}\n")
    sys.exit(2)


def parse_mqtt_config(section: Any) -> MQTTConfig:
    """Parse and validate the ``[mqtt]`` config section."""
    if not isinstance(section, dict):
        _fail("'mqtt' in config must be a table")
        raise AssertionError("unreachable")

    host = section.get("host")
    if not isinstance(host, str) or not host:
        _fail("'mqtt.host' is required")
        raise AssertionError("unreachable")

    port = section.get("port", DEFAULT_MQTT_PORT)
    if not isinstance(port, int) or not (1 <= port <= 65535):
        _fail("'mqtt.port' must be an integer between 1 and 65535")
        raise AssertionError("unreachable")

    qos = section.get("qos", 1)
    if not isinstance(qos, int) or qos not in (0, 1, 2):
        _fail("'mqtt.qos' must be 0, 1, or 2")
        raise AssertionError("unreachable")

    connect_timeout = section.get("connect_timeout", 5.0)
    if not isinstance(connect_timeout, (int, float)) or connect_timeout <= 0:
        _fail("'mqtt.connect_timeout' must be a positive number")
        raise AssertionError("unreachable")

    username = section.get("username")
    password = section.get("password")
    topic_prefix = section.get("topic_prefix", DEFAULT_TOPIC_PREFIX)
    if not isinstance(topic_prefix, str) or not topic_prefix:
        _fail("'mqtt.topic_prefix' must be a non-empty string")
        raise AssertionError("unreachable")

    ca_certs = section.get("ca_certs")
    if ca_certs is not None and not isinstance(ca_certs, str):
        _fail("'mqtt.ca_certs' must be a string path")
        raise AssertionError("unreachable")

    return MQTTConfig(
        host=host,
        port=port,
        username=username if isinstance(username, str) else None,
        password=password if isinstance(password, str) else None,
        tls=bool(section.get("tls", False)),
        ca_certs=ca_certs,
        insecure=bool(section.get("insecure", False)),
        topic_prefix=topic_prefix,
        retain=bool(section.get("retain", True)),
        qos=qos,
        connect_timeout=connect_timeout,
    )


def load_config(config_path: str) -> Config:
    """
    Load and parse configuration file.

    Supports TOML and JSON formats based on file extension.

    Args:
        config_path: Path to configuration file

    Returns:
        Config object with targets and optional MQTT settings

    Raises:
        SystemExit: On configuration loading or parsing errors
    """
    try:
        if config_path.endswith(".toml"):
            if tomllib is None:
                _fail("TOML support requires 'tomli' package for Python < 3.11. Install with: pip install tomli")
            with open(config_path, "rb") as f:
                config_data = tomllib.load(f)
        else:
            # Fallback to JSON for other extensions
            import json

            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
    except FileNotFoundError:
        _fail(f"Config file not found: {config_path}")
    except Exception as e:
        _fail(f"Error loading config file '{config_path}': {e}")

    # Extract targets from config (support nested structure)
    if isinstance(config_data, dict):
        targets = config_data.get("targets", [])
        mqtt_section = config_data.get("mqtt")
    else:
        targets = config_data if isinstance(config_data, list) else []
        mqtt_section = None

    if not isinstance(targets, list):
        _fail("'targets' in config must be a list")

    mqtt = parse_mqtt_config(mqtt_section) if mqtt_section is not None else None

    return Config(targets=targets, mqtt=mqtt)
