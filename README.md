# vlan-probe

VLAN Isolation & Network Permission Probe Tool — standalone project extracted
from the Ansible role in ansible-home-baseline.

## Installation

```bash
pip install -e .
```

## Usage

1. Install or copy to a host.
2. Create a TOML config at `/etc/vlan_probe.toml` or pass `-c` to point to a different file.
3. Run `vlan-probe -f table` or `python -m vlan_probe -f table`.

### Configuration

Configuration uses TOML format for easy human readability and simplicity:

```toml
[[targets]]
name = "Internal - Device A SSH"
vlan = "Internal"
ip = "192.168.1.10"
port = 22
protocol = "tcp"
expected_blocked = true

[[targets]]
name = "Internal - Gateway HTTP"
vlan = "Internal"
ip = "192.168.2.1"
port = 80
protocol = "tcp"
expected_blocked = true

[[targets]]
name = "External - Public DNS"
vlan = "External"
ip = "8.8.8.8"
port = 53
protocol = "udp"
expected_blocked = false
```

### Options

```
-c, --config PATH         Path to config TOML file (default: /etc/vlan_probe.toml)
-f, --format FORMAT       Output format: ndjson, json, or table (default: ndjson)
-t, --timeout SECONDS     Socket connection timeout (default: 2.0)
-s, --strict              Exit with code 1 if any violations occur
--color [auto|always|never]  Colorize output (default: auto)
```

### Examples

```bash
# Display as table
vlan-probe -c ./vlan_probe.toml -f table

# Output JSON
vlan-probe -f json

# Strict mode with custom timeout
vlan-probe -s -t 5.0

# No color output
vlan-probe -f table --color never
```

## Testing

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT (see LICENSE)
