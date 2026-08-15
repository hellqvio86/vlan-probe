"""CLI interface for VLAN probe tool."""

import argparse
import datetime
import json
import os
import sys

from .config import DEFAULT_CONFIG_PATH, load_config
from .probe import get_local_ips, probe_target

# ANSI color codes for interactive (TTY) output.
_COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
}


def colorize(text: str, color: str) -> str:
    """Apply ANSI color to text if color is enabled."""
    if not color:
        return text
    return f"{_COLORS[color]}{text}{_COLORS['reset']}"


def may_colorize() -> bool:
    """Check if output should be colorized."""
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def resolve_color_mode(mode: str) -> bool:
    """Resolve color mode setting to boolean."""
    if mode == "always":
        return True
    if mode == "never":
        return False
    return may_colorize()


def colorize_json_statuses(line: str, color: bool) -> str:
    """Colorize JSON status values in output."""
    if not color:
        return line
    line = line.replace('"status": "PASS"', f'"status": "{colorize("PASS", "green")}"')
    line = line.replace('"status": "FAIL"', f'"status": "{colorize("FAIL", "red")}"')
    return line


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Probe VLAN network access and verify isolation permissions.")
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG_PATH, help="Path to config JSON file")
    parser.add_argument(
        "-f",
        "--format",
        choices=["ndjson", "json", "table"],
        default="ndjson",
        help="Output format (default: ndjson).",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=2.0,
        help="Socket connection timeout in seconds",
    )
    parser.add_argument(
        "-s",
        "--strict",
        action="store_true",
        help="Exit with code 1 if any access violation / test failure occurs",
    )
    parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Colorize table output. auto = on when stdout is a TTY",
    )
    args = parser.parse_args()
    color = resolve_color_mode(args.color)

    targets = load_config(args.config)

    results = []
    violations = []
    local_ips = get_local_ips()

    for target in targets:
        res = probe_target(target, timeout=args.timeout, local_ips=local_ips)
        results.append(res)
        if res["status"] == "FAIL":
            violations.append(res)

        if args.format == "ndjson":
            print(colorize_json_statuses(json.dumps(res), color))

    if args.format == "json":
        summary = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_probed": len(results),
            "passed": len(results) - len(violations),
            "failed": len(violations),
            "violations": [
                {
                    "vlan": v["target_vlan"],
                    "target": v["target_name"],
                    "ip": v["target_ip"],
                    "port": v["port"],
                    "error": v["error"],
                }
                for v in violations
            ],
            "results": results,
        }
        print(colorize_json_statuses(json.dumps(summary, indent=2), color))

    elif args.format == "table":
        if color:
            header = (
                f"{colorize('VLAN', 'cyan'):<12} "
                f"{colorize('TARGET', 'cyan'):<30} "
                f"{colorize('ENDPOINT', 'cyan'):<22} "
                f"{colorize('STATUS', 'cyan'):<8} "
                f"{colorize('DETAILS', 'cyan')}"
            )
            divider = colorize("-" * 90, "cyan")
        else:
            header = f"{'VLAN':<12} {'TARGET':<30} {'ENDPOINT':<22} {'STATUS':<8} {'DETAILS'}"
            divider = "-" * 90
        print(header)
        print(divider)
        for r in results:
            endpoint = f"{r['target_ip']}:{r['port']} ({r['protocol']})"
            details = r["error"] if r["error"] else "OK"
            status = r["status"]
            if color:
                status_color = "red" if status == "FAIL" else "green"
                details_color = "red" if status == "FAIL" else "green"
                status = colorize(str(status), status_color)
                details = colorize(str(details), details_color)
            print(f"{r['target_vlan']:<12} {r['target_name']:<30} {endpoint:<22} {status:<8} {details}")

    if args.strict and violations:
        head = f"{len(violations)} unauthorized connection(s) detected!"
        if color:
            head = colorize(colorize("VLAN ISOLATION VIOLATION FAILURE:", "bold") + " " + head, "red")
        sys.stderr.write(f"\n🚨 {head}\n")
        for v in violations:
            line = f"  - {v['error']}"
            sys.stderr.write((colorize(line, "red") if color else line) + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
