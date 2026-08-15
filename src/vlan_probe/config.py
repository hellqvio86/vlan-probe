"""Configuration loading for vlan_probe."""

import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, NoReturn, Optional

try:
    import tomllib  # Python 3.11+  # pragma: no cover
except ImportError:  # pragma: no cover
    try:
        import tomli as tomllib  # Fallback for Python < 3.11
    except ImportError:
        tomllib = None

DEFAULT_CONFIG_PATH = "/etc/vlan_probe.toml"

DEFAULT_MQTT_PORT = 1883
DEFAULT_TOPIC_PREFIX = "vlan-probe"

DEFAULT_TIMEOUT = 2.0
DEFAULT_FORMAT = "ndjson"
VALID_FORMATS = ("ndjson", "json", "table")

ENV_CONFIG_PATH = "VLAN_PROBE_CONFIG"
ENV_TIMEOUT = "VLAN_PROBE_TIMEOUT"
ENV_FORMAT = "VLAN_PROBE_FORMAT"
ENV_STRICT = "VLAN_PROBE_STRICT"

ENV_MQTT_HOST = "VLAN_PROBE_MQTT_HOST"
ENV_MQTT_PORT = "VLAN_PROBE_MQTT_PORT"
ENV_MQTT_USERNAME = "VLAN_PROBE_MQTT_USERNAME"
ENV_MQTT_PASSWORD = "VLAN_PROBE_MQTT_PASSWORD"
ENV_MQTT_TLS = "VLAN_PROBE_MQTT_TLS"
ENV_MQTT_CA_CERTS = "VLAN_PROBE_MQTT_CA_CERTS"
ENV_MQTT_INSECURE = "VLAN_PROBE_MQTT_INSECURE"
ENV_MQTT_TOPIC_PREFIX = "VLAN_PROBE_MQTT_TOPIC_PREFIX"
ENV_MQTT_RETAIN = "VLAN_PROBE_MQTT_RETAIN"
ENV_MQTT_QOS = "VLAN_PROBE_MQTT_QOS"
ENV_MQTT_CONNECT_TIMEOUT = "VLAN_PROBE_MQTT_CONNECT_TIMEOUT"

MQTT_ENV_VARS = (
    ENV_MQTT_HOST,
    ENV_MQTT_PORT,
    ENV_MQTT_USERNAME,
    ENV_MQTT_PASSWORD,
    ENV_MQTT_TLS,
    ENV_MQTT_CA_CERTS,
    ENV_MQTT_INSECURE,
    ENV_MQTT_TOPIC_PREFIX,
    ENV_MQTT_RETAIN,
    ENV_MQTT_QOS,
    ENV_MQTT_CONNECT_TIMEOUT,
)

ALL_ENV_VARS = (ENV_CONFIG_PATH, ENV_TIMEOUT, ENV_FORMAT, ENV_STRICT) + MQTT_ENV_VARS

_TRUE_VALUES = ("1", "true", "yes", "on")


def _env_bool(value: Optional[str]) -> bool:
    """Interpret an environment variable as a boolean."""
    return value is not None and value.strip().lower() in _TRUE_VALUES


def default_config_path() -> str:
    """Return the config path from ``VLAN_PROBE_CONFIG`` or the default."""
    return os.environ.get(ENV_CONFIG_PATH) or DEFAULT_CONFIG_PATH


def default_timeout() -> float:
    """Return the probe timeout from ``VLAN_PROBE_TIMEOUT`` or the default."""
    raw = os.environ.get(ENV_TIMEOUT)
    if raw is None:
        return DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        _fail("'VLAN_PROBE_TIMEOUT' must be a positive number")
    if value <= 0:
        _fail("'VLAN_PROBE_TIMEOUT' must be a positive number")
    return value


def default_format() -> str:
    """Return the output format from ``VLAN_PROBE_FORMAT`` or the default."""
    value = os.environ.get(ENV_FORMAT) or DEFAULT_FORMAT
    if value not in VALID_FORMATS:
        _fail("'VLAN_PROBE_FORMAT' must be one of: " + ", ".join(VALID_FORMATS))
    return value


def default_strict() -> bool:
    """Return strict mode from ``VLAN_PROBE_STRICT`` or the default."""
    return _env_bool(os.environ.get(ENV_STRICT))


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


def _fail(message: str) -> NoReturn:
    sys.stderr.write(f"Error: {message}\n")
    sys.exit(2)


def _boolish(value: Any) -> bool:
    """Coerce a TOML/JSON or environment value into a boolean."""
    if isinstance(value, str):
        return _env_bool(value)
    return bool(value)


def _collect_mqtt_env_overrides() -> Dict[str, Any]:
    """Return MQTT settings explicitly provided via environment variables."""
    overrides: Dict[str, Any] = {}

    if ENV_MQTT_HOST in os.environ:
        overrides["host"] = os.environ[ENV_MQTT_HOST]

    if ENV_MQTT_PORT in os.environ:
        try:
            port = int(os.environ[ENV_MQTT_PORT])
        except ValueError:
            _fail("'VLAN_PROBE_MQTT_PORT' must be an integer between 1 and 65535")
        overrides["port"] = port

    if ENV_MQTT_USERNAME in os.environ:
        overrides["username"] = os.environ[ENV_MQTT_USERNAME]
    if ENV_MQTT_PASSWORD in os.environ:
        overrides["password"] = os.environ[ENV_MQTT_PASSWORD]
    if ENV_MQTT_TLS in os.environ:
        overrides["tls"] = _env_bool(os.environ[ENV_MQTT_TLS])
    if ENV_MQTT_CA_CERTS in os.environ:
        overrides["ca_certs"] = os.environ[ENV_MQTT_CA_CERTS]
    if ENV_MQTT_INSECURE in os.environ:
        overrides["insecure"] = _env_bool(os.environ[ENV_MQTT_INSECURE])
    if ENV_MQTT_TOPIC_PREFIX in os.environ:
        overrides["topic_prefix"] = os.environ[ENV_MQTT_TOPIC_PREFIX]
    if ENV_MQTT_RETAIN in os.environ:
        overrides["retain"] = _env_bool(os.environ[ENV_MQTT_RETAIN])

    if ENV_MQTT_QOS in os.environ:
        try:
            qos = int(os.environ[ENV_MQTT_QOS])
        except ValueError:
            _fail("'VLAN_PROBE_MQTT_QOS' must be 0, 1, or 2")
        overrides["qos"] = qos

    if ENV_MQTT_CONNECT_TIMEOUT in os.environ:
        try:
            connect_timeout = float(os.environ[ENV_MQTT_CONNECT_TIMEOUT])
        except ValueError:
            _fail("'VLAN_PROBE_MQTT_CONNECT_TIMEOUT' must be a positive number")
        overrides["connect_timeout"] = connect_timeout

    return overrides


def parse_mqtt_config(section: Any, env_overrides: Optional[Dict[str, Any]] = None) -> MQTTConfig:
    """Parse and validate the ``[mqtt]`` config section, applying env overrides."""
    if not isinstance(section, dict):
        _fail("'mqtt' in config must be a table")
    overrides = env_overrides or {}

    host = overrides.get("host", section.get("host"))
    if not isinstance(host, str) or not host:
        _fail("'mqtt.host' is required")

    port = overrides.get("port", section.get("port", DEFAULT_MQTT_PORT))
    if not isinstance(port, int) or not (1 <= port <= 65535):
        _fail("'mqtt.port' must be an integer between 1 and 65535")

    qos = overrides.get("qos", section.get("qos", 1))
    if not isinstance(qos, int) or qos not in (0, 1, 2):
        _fail("'mqtt.qos' must be 0, 1, or 2")

    connect_timeout = overrides.get("connect_timeout", section.get("connect_timeout", 5.0))
    if not isinstance(connect_timeout, (int, float)) or connect_timeout <= 0:
        _fail("'mqtt.connect_timeout' must be a positive number")

    username = overrides.get("username", section.get("username"))
    password = overrides.get("password", section.get("password"))
    topic_prefix = overrides.get("topic_prefix", section.get("topic_prefix", DEFAULT_TOPIC_PREFIX))
    if not isinstance(topic_prefix, str) or not topic_prefix:
        _fail("'mqtt.topic_prefix' must be a non-empty string")

    ca_certs = overrides.get("ca_certs", section.get("ca_certs"))
    if ca_certs is not None and not isinstance(ca_certs, str):
        _fail("'mqtt.ca_certs' must be a string path")

    return MQTTConfig(
        host=host,
        port=port,
        username=username if isinstance(username, str) else None,
        password=password if isinstance(password, str) else None,
        tls=_boolish(overrides.get("tls", section.get("tls", False))),
        ca_certs=ca_certs,
        insecure=_boolish(overrides.get("insecure", section.get("insecure", False))),
        topic_prefix=topic_prefix,
        retain=_boolish(overrides.get("retain", section.get("retain", True))),
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

    mqtt = _build_mqtt_config(mqtt_section)

    return Config(targets=targets, mqtt=mqtt)


def _build_mqtt_config(mqtt_section: Any) -> Optional[MQTTConfig]:
    """Build an MQTTConfig from the config file section and env overrides."""
    env_overrides = _collect_mqtt_env_overrides()
    if mqtt_section is not None:
        return parse_mqtt_config(mqtt_section, env_overrides)
    if "host" in env_overrides:
        return parse_mqtt_config({}, env_overrides)
    return None
