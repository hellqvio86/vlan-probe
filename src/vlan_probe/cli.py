"""CLI interface for VLAN probe tool."""

import argparse
import datetime
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from . import __version__
from .config import (
    VALID_FORMATS,
    default_concurrency,
    default_config_path,
    default_format,
    default_strict,
    default_timeout,
    load_config,
)
from .mqtt_report import MQTTPublishError, build_messages, publish_to_mqtt
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
    line = line.replace('"status": "SKIP"', f'"status": "{colorize("SKIP", "yellow")}"')
    return line


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Probe VLAN network access and verify isolation permissions.")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-c", "--config", default=default_config_path(), help="Path to config TOML/JSON file")
    parser.add_argument(
        "-f",
        "--format",
        choices=list(VALID_FORMATS),
        default=default_format(),
        help="Output format (default: ndjson).",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=default_timeout(),
        help="Socket connection timeout in seconds",
    )
    parser.add_argument(
        "-j",
        "--concurrency",
        type=int,
        default=default_concurrency(),
        help="Number of concurrent worker threads (default: 10)",
    )
    parser.add_argument(
        "-s",
        "--strict",
        action="store_true",
        default=default_strict(),
        help="Exit with code 1 if any access violation / test failure occurs",
    )
    parser.add_argument(
        "--mqtt",
        action="store_true",
        help="Publish probe results to MQTT (requires a [mqtt] config section)",
    )
    parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Colorize table output. auto = on when stdout is a TTY",
    )
    args = parser.parse_args()
    color = resolve_color_mode(args.color)

    config = load_config(args.config)
    targets = config.targets

    if args.mqtt and config.mqtt is None:
        sys.stderr.write("Error: --mqtt requires a [mqtt] section in the config file\n")
        sys.exit(2)

    local_ips = get_local_ips()
    max_workers = max(1, args.concurrency)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(
            executor.map(
                lambda target: probe_target(target, timeout=args.timeout, local_ips=local_ips),
                targets,
            )
        )

    violations = [r for r in results if r["status"] == "FAIL"]
    skipped = [r for r in results if r["status"] == "SKIP"]
    passed = [r for r in results if r["status"] == "PASS"]

    summary = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_probed": len(results),
        "passed": len(passed),
        "failed": len(violations),
        "skipped": len(skipped),
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

    mqtt_res = None
    mqtt_failed = False
    if args.mqtt:
        assert config.mqtt is not None
        messages = build_messages(results, summary, config.mqtt)
        mqtt_error = None
        try:
            publish_to_mqtt(config.mqtt, messages)
        except MQTTPublishError as e:
            mqtt_error = str(e)
            mqtt_failed = True

        mqtt_res = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "target_name": f"MQTT Report ({config.mqtt.host}:{config.mqtt.port})",
            "target_vlan": "MQTT",
            "target_ip": config.mqtt.host,
            "port": config.mqtt.port,
            "protocol": "tcp",
            "reachable": not mqtt_failed,
            "expected_blocked": False,
            "status": "FAIL" if mqtt_failed else "PASS",
            "published": len(messages) if not mqtt_failed else 0,
            "error": mqtt_error,
        }

    if args.format == "ndjson":
        for res in results:
            print(colorize_json_statuses(json.dumps(res), color))
        if mqtt_res:
            print(colorize_json_statuses(json.dumps(mqtt_res), color))

    elif args.format == "json":
        if mqtt_res:
            summary["mqtt"] = mqtt_res
        print(colorize_json_statuses(json.dumps(summary, indent=2), color))

    elif args.format == "table":
        all_rows = list(results)
        if mqtt_res:
            all_rows.append(mqtt_res)

        vlan_w = max(12, max((len(str(r["target_vlan"])) for r in all_rows), default=12))
        name_w = max(30, max((len(str(r["target_name"])) for r in all_rows), default=30))
        ep_w = max(22, max((len(f"{r['target_ip']}:{r['port']} ({r['protocol']})") for r in all_rows), default=22))
        divider_len = vlan_w + name_w + ep_w + 8 + 15 + 4

        if color:
            header = (
                f"{colorize('VLAN'.ljust(vlan_w), 'cyan')} "
                f"{colorize('TARGET'.ljust(name_w), 'cyan')} "
                f"{colorize('ENDPOINT'.ljust(ep_w), 'cyan')} "
                f"{colorize('STATUS'.ljust(8), 'cyan')} "
                f"{colorize('DETAILS', 'cyan')}"
            )
            divider = colorize("-" * divider_len, "cyan")
        else:
            header = f"{'VLAN':<{vlan_w}} {'TARGET':<{name_w}} {'ENDPOINT':<{ep_w}} {'STATUS':<8} {'DETAILS'}"
            divider = "-" * divider_len
        print(header)
        print(divider)
        for r in results:
            endpoint = f"{r['target_ip']}:{r['port']} ({r['protocol']})"
            details = r["error"] if r["error"] else "OK"
            status = str(r["status"])
            status_text = f"{status:<8}"
            if color:
                if status == "FAIL":
                    status_disp = colorize(status_text, "red")
                    details_disp = colorize(str(details), "red")
                elif status == "SKIP":
                    status_disp = colorize(status_text, "yellow")
                    details_disp = colorize(str(details), "yellow")
                else:
                    status_disp = colorize(status_text, "green")
                    details_disp = colorize(str(details), "green")
            else:
                status_disp = status_text
                details_disp = str(details)
            vlan_str = f"{r['target_vlan']:<{vlan_w}}"
            name_str = f"{r['target_name']:<{name_w}}"
            ep_str = f"{endpoint:<{ep_w}}"
            print(f"{vlan_str} {name_str} {ep_str} {status_disp} {details_disp}")
        if mqtt_res:
            endpoint = f"{mqtt_res['target_ip']}:{mqtt_res['port']} ({mqtt_res['protocol']})"
            details = mqtt_res["error"] if mqtt_res["error"] else f"Published {mqtt_res['published']} msg(s)"
            status = str(mqtt_res["status"])
            status_text = f"{status:<8}"
            if color:
                status_color = "red" if status == "FAIL" else "green"
                details_color = "red" if status == "FAIL" else "green"
                status_disp = colorize(status_text, status_color)
                details_disp = colorize(str(details), details_color)
            else:
                status_disp = status_text
                details_disp = str(details)
            mvlan_str = f"{mqtt_res['target_vlan']:<{vlan_w}}"
            mname_str = f"{mqtt_res['target_name']:<{name_w}}"
            mep_str = f"{endpoint:<{ep_w}}"
            print(f"{mvlan_str} {mname_str} {mep_str} {status_disp} {details_disp}")

    if args.strict and violations:
        head = f"{len(violations)} unauthorized connection(s) detected!"
        if color:
            head = colorize(colorize("VLAN ISOLATION VIOLATION FAILURE:", "bold") + " " + head, "red")
        sys.stderr.write(f"\n🚨 {head}\n")
        for v in violations:
            line = f"  - {v['error']}"
            sys.stderr.write((colorize(line, "red") if color else line) + "\n")
        sys.exit(1)

    if mqtt_failed:
        sys.exit(2)


if __name__ == "__main__":
    main()
