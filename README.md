# vlan-probe 🛡️

VLAN Isolation & Network Permission Probe Tool — verify your firewall rules by
probing target VLAN subnets, IPs, and ports from the host and reporting any
unauthorized inter-VLAN access.

[![PyPI - Version](https://img.shields.io/pypi/v/vlan-probe?color=blue)](https://pypi.org/project/vlan-probe/)
[![PyPI - Python Versions](https://img.shields.io/pypi/pyversions/vlan-probe)](https://pypi.org/project/vlan-probe/)
[![PyPI - License](https://img.shields.io/pypi/l/vlan-probe)](https://github.com/hellqvio86/vlan-probe/blob/main/LICENSE)
[![CI/CD](https://img.shields.io/github/actions/workflow/status/hellqvio86/vlan-probe/ci.yml?branch=main&label=CI/CD)](https://github.com/hellqvio86/vlan-probe/actions/workflows/ci.yml)

`vlan-probe` is a command-line tool. Install it with [pipx](https://pipx.pypa.io/)
so it runs in an isolated environment and the `vlan-probe` command is available
on your `PATH`.

## Requirements

- Python 3.10 or newer

## Installation

### Install with pipx (recommended)

```bash
pipx install vlan-probe
```

Upgrade to a newer release:

```bash
pipx upgrade vlan-probe
```

If you do not already have pipx, install it first (macOS/Homebrew, Debian/Ubuntu
or Arch examples; see the [pipx docs](https://pipx.pypa.io/) for other systems):

```bash
brew install pipx && pipx ensurepath
# or
apt install pipx && pipx ensurepath
# or
pacman -S python-pipx && pipx ensurepath
```

### Install from source

```bash
# with pipx
pipx install .

# with uv (alternative)
uv tool install .

# or install directly into your environment
pip install .
```

## Usage 📡

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

For each target:

- `expected_blocked = true` — the probe expects the firewall to **deny** access;
  a reachable target is reported as a violation 🔴.
- `expected_blocked = false` — the probe expects the firewall to **allow** access;
  an unreachable target is reported as a failure 🔴.

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

## Development 🧑‍💻

```bash
uv sync          # install dev dependencies
uv run pytest    # run tests
uv run ruff check . && uv run ruff format --check .   # lint
uv run mypy src  # type check
```

## License

MIT (see LICENSE)