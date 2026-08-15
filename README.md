# vlan-probe 🛡️

> **VLAN Isolation & Network Permission Probe Tool** — verify your firewall
> rules by probing target VLAN subnets, IPs, and ports from the host, and get
> alerted to any unauthorized inter-VLAN access.

[![PyPI - Version](https://img.shields.io/pypi/v/vlan-probe?color=blue)](https://pypi.org/project/vlan-probe/)
[![PyPI - Python Versions](https://img.shields.io/pypi/pyversions/vlan-probe)](https://pypi.org/project/vlan-probe/)
[![PyPI - License](https://img.shields.io/pypi/l/vlan-probe)](https://github.com/hellqvio86/vlan-probe/blob/main/LICENSE.md)
[![CI/CD](https://img.shields.io/github/actions/workflow/status/hellqvio86/vlan-probe/ci.yml?branch=main&label=CI/CD)](https://github.com/hellqvio86/vlan-probe/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/hellqvio86/vlan-probe/blob/main/README.md)

---

## ✨ Features

- **Multi-protocol probing** — `tcp`, `udp` (DNS-aware on port 53), `icmp`
  (ping), and `sctp`.
- **Policy-first configuration** — declare what *should* be blocked vs.
  reachable; every deviation is reported as a violation 🔴.
- **Flexible output** — human-friendly `table`, structured `json`, or
  streaming `ndjson`.
- **Alerting built-in** — `--strict` exit codes for automation, plus scheduled
  **MQTT reporting** via `systemd` timers 📡.
- **Boring & reliable** — typed Python 3.10+, zero long-running daemons, 100%
  test coverage.

## 📑 Table of contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
- [Scheduled MQTT reporting](#scheduled-mqtt-reporting-)
- [Development](#development-)

---

## Requirements

- **Python 3.10 or newer**
- Linux (uses the `ip` and `ping` utilities)

## Installation

### Install with pipx (recommended)

`vlan-probe` is a command-line tool — [pipx](https://pipx.pypa.io/) runs it in
an isolated environment while keeping the `vlan-probe` command on your `PATH`.

```bash
pipx install vlan-probe
```

Upgrade to a newer release:

```bash
pipx upgrade vlan-probe
```

Don't have pipx yet? Install it first:

```bash
brew install pipx && pipx ensurepath      # macOS/Homebrew
apt install pipx && pipx ensurepath       # Debian/Ubuntu
pacman -S python-pipx && pipx ensurepath  # Arch
```

### Install from source

```bash
pipx install .          # via pipx
uv tool install .       # via uv
pip install .           # into the active environment
```

## Quick start

```bash
# 1. copy the example config and edit it to match your network
cp vlan_probe.toml.example /etc/vlan_probe.toml

# 2. probe everything and show a human-friendly table
vlan-probe -f table

# 3. or go headless: JSON to stdout, exit 1 on any violation
vlan-probe -f json -s
```

## Configuration

Configuration lives in a single [TOML](https://toml.io/) file — readable,
diff-able, and easy to keep in git. By default it is read from
`/etc/vlan_probe.toml`; use `-c <path>` for another location.

```toml
[[targets]]
name = "Internal - Device A SSH"
vlan = "Internal"
ip = "10.10.1.10"
port = 22
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

Each target declares the firewall policy it expects:

| `expected_blocked` | Policy        | Reported when…                                       |
| ------------------ | ------------- | ---------------------------------------------------- |
| `true`             | **deny**      | target is *reachable* → violation 🔴                  |
| `false`            | **allow**     | target is *unreachable* → failure 🔴                  |

**Supported protocols:** `tcp` · `udp` (probed with a real DNS query on port
53) · `icmp` (via `ping`) · `sctp`.

## Usage

```
-c, --config PATH         Path to config TOML file (default: /etc/vlan_probe.toml)
-f, --format FORMAT       Output format: ndjson, json, or table (default: ndjson)
-t, --timeout SECONDS     Socket connection timeout (default: 2.0)
-s, --strict              Exit with code 1 if any violations occur
--mqtt                    Publish results to MQTT (requires [mqtt] config section)
--color [auto|always|never]  Colorize output (default: auto)
```

```bash
# table output
vlan-probe -c ./vlan_probe.toml -f table

# json output
vlan-probe -f json

# strict mode with a custom timeout
vlan-probe -s -t 5.0

# no color
vlan-probe -f table --color never
```

### Exit codes

| Code | Meaning                                             |
| ---- | --------------------------------------------------- |
| `0`  | all checks passed                                   |
| `1`  | violations detected (with `--strict`)               |
| `2`  | configuration error or MQTT delivery failure        |

### Output formats

Table (IPs are fictional):

```text
VLAN         TARGET                         ENDPOINT               STATUS   DETAILS
------------------------------------------------------------------------------------------
Internal     Internal - Device A SSH        10.10.1.10:22 (tcp)    PASS     OK
Internal     Internal - DNS Server          10.10.1.1:53 (udp)     PASS     OK
IoT          IoT - Device B                 10.10.2.50:80 (tcp)    PASS     OK
DMZ          DMZ - Web Server               10.10.4.50:80 (tcp)    FAIL     EXPECTED_CONNECTIVITY_FAILED: Failed to connect to DMZ - Web Server (10.10.4.50:80)
External     External - Public DNS          8.8.8.8:53 (udp)       PASS     OK
```

JSON — a run summary with totals and violations:

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
    }
  ]
}
```

NDJSON — one object per probed target, ideal for streaming/ingestion:

```json
{"timestamp": "2026-08-15T07:55:15.797713+00:00", "target_name": "Internal - Device A SSH", "target_vlan": "Internal", "target_ip": "10.10.1.10", "port": 22, "protocol": "tcp", "reachable": false, "expected_blocked": true, "status": "PASS", "latency_ms": 1001.0, "error": null}
```

Strict mode (`-s`) writes failures to stderr and exits with code 1:

```text
🚨 2 unauthorized connection(s) detected!
  - EXPECTED_CONNECTIVITY_FAILED: Failed to connect to DMZ - Web Server (10.10.4.50:80)
  - EXPECTED_CONNECTIVITY_FAILED: Failed to connect to DMZ - Web Server HTTPS (10.10.4.50:443)
```

## Scheduled MQTT reporting ⏱️

Run the probe on a schedule and publish results to an MQTT broker so
dashboards and automations can track VLAN isolation state over time. A
`systemd` timer wakes a short-lived process that probes, publishes, and exits —
no daemon, no state to babysit.

Add an `[mqtt]` section to the config:

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

…and run with `--mqtt`:

```bash
vlan-probe --mqtt
```

**Topics published** (all retained at QoS 1):

- `vlan-probe/<hostname>/summary` — run summary (totals + violations)
- `vlan-probe/<hostname>/targets/<vlan>/<target>` — one message per target

> A failed MQTT delivery is fatal (exit code 2); probe violations in strict
> mode still exit 1. `--mqtt` without an `[mqtt]` section is a config error.

### systemd timer

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

**Ops tips:**

- `journalctl -u vlan-probe` — probe + delivery logs per run
- `systemctl list-timers vlan-probe` — next scheduled run
- Broker credentials: `[mqtt]` in the config (chmod 600) or a systemd
  `EnvironmentFile`

---

## Development 🧑‍💻

The repository ships a [`Makefile`](Makefile) wrapping `uv` — that's the
supported way to work in this project.

| Command           | What it does                                            |
| ----------------- | ------------------------------------------------------- |
| `make venv`       | create the virtualenv and install dev dependencies      |
| `make lint`       | ruff lint **and** format check                          |
| `make format`     | auto-format the code with ruff                          |
| `make test`       | mypy type-check + pytest with 100% coverage gate        |
| `make run`        | run the CLI, e.g. `make run ARGS="-f table"`            |
| `make build`      | build sdist + wheel                                     |
| `make publish`    | build and publish to PyPI                               |
| `make install`    | install the package into a uv tool environment          |
| `make clean`      | remove the venv and build/cache artifacts               |

```bash
make venv    # one-time setup
make lint    # before pushing
make test    # before pushing
```

### Test coverage 🛡️

Every code path is covered by a meaningful test — real loopback sockets and
real config files, mocking only system boundaries. `pytest` fails if coverage
drops below 100% (`--cov-fail-under=100`). Run the suite with a coverage
report:

```bash
make test                      # mypy + pytest with coverage
make run ARGS="-f table"       # try it out
```

## License

[MIT](LICENSE.md)