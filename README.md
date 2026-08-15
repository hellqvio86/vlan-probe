# vlan-probe 🛡️

VLAN Isolation & Network Permission Probe Tool — verify your firewall rules by
probing target VLAN subnets, IPs, and ports from the host and reporting any
unauthorized inter-VLAN access.

[![PyPI - Version](https://img.shields.io/pypi/v/vlan-probe?color=blue)](https://pypi.org/project/vlan-probe/)
[![PyPI - Python Versions](https://img.shields.io/pypi/pyversions/vlan-probe)](https://pypi.org/project/vlan-probe/)
[![PyPI - License](https://img.shields.io/pypi/l/vlan-probe)](https://github.com/hellqvio86/vlan-probe/blob/main/LICENSE)
[![CI/CD](https://img.shields.io/github/actions/workflow/status/hellqvio86/vlan-probe/ci.yml?branch=main&label=CI/CD)](https://github.com/hellqvio86/vlan-probe/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/hellqvio86/vlan-probe/blob/main/README.md)

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
ip = "10.10.1.10"
port = 22
protocol = "tcp"
expected_blocked = true

[[targets]]
name = "Internal - Gateway HTTP"
vlan = "Internal"
ip = "10.10.1.1"
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

[[targets]]
name = "Internal - Gateway Ping"
vlan = "Internal"
ip = "10.10.1.1"
port = 0
protocol = "icmp"
expected_blocked = true

[[targets]]
name = "Internal - Diameter Signalling"
vlan = "Internal"
ip = "10.10.1.20"
port = 3868
protocol = "sctp"
expected_blocked = false
```

For each target:

- `expected_blocked = true` — the probe expects the firewall to **deny** access;
  a reachable target is reported as a violation 🔴.
- `expected_blocked = false` — the probe expects the firewall to **allow** access;
  an unreachable target is reported as a failure 🔴.

Supported protocols: `tcp`, `udp` (with DNS probing on port 53), `icmp` (ping),
and `sctp`.

### Options

```
-c, --config PATH         Path to config TOML file (default: /etc/vlan_probe.toml)
-f, --format FORMAT       Output format: ndjson, json, or table (default: ndjson)
-t, --timeout SECONDS     Socket connection timeout (default: 2.0)
-s, --strict              Exit with code 1 if any violations occur
--mqtt                    Publish results to MQTT (requires [mqtt] config section)
--color [auto|always|never]  Colorize output (default: auto)
```

### Scheduled MQTT reporting ⏱️

Run the probe on a schedule and publish results to an MQTT broker so dashboards
and automations can track VLAN isolation state over time. Scheduling is handled
by a `systemd` timer — each run is a short-lived process that probes, publishes,
and exits.

Add an `[mqtt]` section to the config file:

```toml
[mqtt]
host = "mqtt.example.com"
port = 8883
username = "vlan-probe"               # optional
password = "s3cret"                   # optional
tls = true                            # optional, default false
ca_certs = "/etc/ssl/certs/ca-certificates.crt"  # optional
insecure = false                      # optional
topic_prefix = "vlan-probe"           # optional, default "vlan-probe"
retain = true                         # optional, default true
qos = 1                               # optional, default 1
connect_timeout = 5.0                 # optional, default 5.0
```

Then run with `--mqtt`:

```bash
vlan-probe --mqtt
```

Topics published (all retained at QoS 1):

- `vlan-probe/<hostname>/summary` — run summary JSON (totals + violations)
- `vlan-probe/<hostname>/targets/<vlan>/<target>` — one message per probed target

A failed MQTT delivery is fatal (exit code 2); probe violations in strict mode
still exit 1. `--mqtt` without an `[mqtt]` section is a config error.

#### systemd timer

Ship the example units and enable the timer (adjust the interval in
`vlan-probe.timer`, default every 5 minutes):

```bash
# system-wide (root)
sudo cp deploy/systemd/vlan-probe.service deploy/systemd/vlan-probe.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vlan-probe.timer

# user (no root)
mkdir -p ~/.config/systemd/user
cp deploy/systemd/user/vlan-probe.service deploy/systemd/user/vlan-probe.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now vlan-probe.timer
```

Ops:

- `journalctl -u vlan-probe` — probe + delivery logs per run.
- `systemctl list-timers vlan-probe` — next scheduled run.
- Broker credentials: `[mqtt]` in the config (chmod 600) or a systemd
  `EnvironmentFile`.

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

### Example runs

Table output (IPs are fictional):

```text
VLAN         TARGET                         ENDPOINT               STATUS   DETAILS
------------------------------------------------------------------------------------------
Internal     Internal - Device A SSH        10.10.1.10:22 (tcp)    PASS     OK
Internal     Internal - Device A HTTP       10.10.1.10:8080 (tcp)  PASS     OK
Internal     Internal - DNS Server          10.10.1.1:53 (udp)     PASS     OK
Internal     Internal - Gateway SSH         10.10.1.1:22 (tcp)     PASS     OK
Internal     Internal - Gateway HTTPS       10.10.1.1:443 (tcp)    PASS     OK
Internal     Internal - Gateway HTTP        10.10.1.1:80 (tcp)     PASS     OK
IoT          IoT - Device B                 10.10.2.50:80 (tcp)    PASS     OK
IoT          IoT - Device C                 10.10.2.100:80 (tcp)   PASS     OK
Guest        Guest - Gateway                10.10.3.1:80 (tcp)     PASS     OK
DMZ          DMZ - Web Server               10.10.4.50:80 (tcp)    FAIL     EXPECTED_CONNECTIVITY_FAILED: Failed to connect to DMZ - Web Server (10.10.4.50:80)
DMZ          DMZ - Web Server HTTPS         10.10.4.50:443 (tcp)   FAIL     EXPECTED_CONNECTIVITY_FAILED: Failed to connect to DMZ - Web Server HTTPS (10.10.4.50:443)
External     External - Public DNS          8.8.8.8:53 (udp)       PASS     OK
```

JSON output:

```json
{
  "timestamp": "2026-08-15T07:56:17.397044+00:00",
  "total_probed": 12,
  "passed": 10,
  "failed": 2,
  "violations": [
    {
      "vlan": "DMZ",
      "target": "DMZ - Web Server",
      "ip": "10.10.4.50",
      "port": 80,
      "error": "EXPECTED_CONNECTIVITY_FAILED: Failed to connect to DMZ - Web Server (10.10.4.50:80)"
    },
    {
      "vlan": "DMZ",
      "target": "DMZ - Web Server HTTPS",
      "ip": "10.10.4.50",
      "port": 443,
      "error": "EXPECTED_CONNECTIVITY_FAILED: Failed to connect to DMZ - Web Server HTTPS (10.10.4.50:443)"
    }
  ]
}
```

NDJSON output (one JSON object per probed target):

```json
{"timestamp": "2026-08-15T07:55:15.797713+00:00", "target_name": "Internal - Device A SSH", "target_vlan": "Internal", "target_ip": "10.10.1.10", "port": 22, "protocol": "tcp", "reachable": false, "expected_blocked": true, "status": "PASS", "latency_ms": 1001.0, "error": null}
```

Strict mode (`-s`) writes failures to stderr and exits with code 1:

```text
🚨 2 unauthorized connection(s) detected!
  - EXPECTED_CONNECTIVITY_FAILED: Failed to connect to DMZ - Web Server (10.10.4.50:80)
  - EXPECTED_CONNECTIVITY_FAILED: Failed to connect to DMZ - Web Server HTTPS (10.10.4.50:443)
```

## Development 🧑‍💻

```bash
uv sync          # install dev dependencies
uv run pytest    # run tests
uv run ruff check . && uv run ruff format --check .   # lint
uv run mypy src  # type check
```

### Test coverage 🛡️

Every code path is covered by a test; `pytest` fails if coverage drops below
100% (`--cov-fail-under=100`). Run the suite with coverage:

```bash
uv run pytest --cov=src/vlan_probe --cov-report=term-missing
```

## License

[MIT](LICENSE)