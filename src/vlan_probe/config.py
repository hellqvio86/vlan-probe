"""Configuration loading for vlan_probe."""

import sys
from typing import Any, Dict, List

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # Fallback for Python < 3.11
    except ImportError:
        tomllib = None

DEFAULT_CONFIG_PATH = "/etc/vlan_probe.toml"


def load_config(config_path: str) -> List[Dict[str, Any]]:
    """
    Load and parse configuration file.

    Supports TOML and JSON formats based on file extension.

    Args:
        config_path: Path to configuration file

    Returns:
        List of target dictionaries

    Raises:
        SystemExit: On configuration loading or parsing errors
    """
    try:
        if config_path.endswith(".toml"):
            if tomllib is None:
                sys.stderr.write(
                    "Error: TOML support requires 'tomli' package for Python < 3.11. "
                    "Install with: pip install tomli\n"
                )
                sys.exit(2)
            with open(config_path, "rb") as f:
                config_data = tomllib.load(f)
        else:
            # Fallback to JSON for other extensions
            import json

            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
    except FileNotFoundError:
        sys.stderr.write(f"Error: Config file not found: {config_path}\n")
        sys.exit(2)
    except Exception as e:
        sys.stderr.write(f"Error loading config file '{config_path}': {e}\n")
        sys.exit(2)

    # Extract targets from config (support nested structure)
    if isinstance(config_data, dict):
        targets = config_data.get("targets", [])
    else:
        targets = config_data if isinstance(config_data, list) else []

    if not isinstance(targets, list):
        sys.stderr.write("Error: 'targets' in config must be a list\n")
        sys.exit(2)

    return targets
