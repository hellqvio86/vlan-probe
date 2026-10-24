"""Prometheus textfile collector reporting for vlan_probe."""

import datetime
import os
from typing import Dict, List, Optional

from .config import PrometheusConfig


class PrometheusWriteError(Exception):
    """Raised when writing Prometheus metrics to the textfile collector path fails."""


def escape_label_value(value: str) -> str:
    """Escape a Prometheus label value per the text exposition format."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_labels(labels: Dict[str, str]) -> str:
    """Format a dictionary of Prometheus labels as ``{k1="v1",k2="v2"}``."""
    parts = [f'{key}="{escape_label_value(val)}"' for key, val in labels.items()]
    return "{" + ",".join(parts) + "}"


def _status_to_value(status: str) -> int:
    """Map probe status string to numeric Prometheus gauge value."""
    if status == "PASS":
        return 1
    if status == "FAIL":
        return 0
    return -1


def _summary_int(summary: Dict[str, object], key: str, default: int) -> int:
    """Extract an integer counter from summary dict or return default."""
    val = summary.get(key)
    return val if isinstance(val, int) else default


def build_prometheus_metrics(
    results: List[Dict[str, object]],
    summary: Dict[str, object],
    timestamp_seconds: Optional[float] = None,
) -> str:
    """Build Prometheus text exposition payload from probe results and summary."""
    lines: List[str] = [
        "# HELP vlan_probe_target_status Probe compliance status per target (1 = PASS, 0 = FAIL, -1 = SKIP).",
        "# TYPE vlan_probe_target_status gauge",
    ]
    for res in results:
        labels = {
            "vlan": str(res.get("target_vlan", "")),
            "target": str(res.get("target_name", "")),
            "ip": str(res.get("target_ip", "")),
            "port": str(res.get("port", 0)),
            "protocol": str(res.get("protocol", "tcp")),
            "expected_blocked": "true" if bool(res.get("expected_blocked", False)) else "false",
        }
        status_val = _status_to_value(str(res.get("status", "")))
        lines.append(f"vlan_probe_target_status{_format_labels(labels)} {status_val}")

    lines.extend(
        [
            "# HELP vlan_probe_target_reachable Target endpoint reachability (1 = reachable, 0 = blocked).",
            "# TYPE vlan_probe_target_reachable gauge",
        ]
    )
    for res in results:
        labels = {
            "vlan": str(res.get("target_vlan", "")),
            "target": str(res.get("target_name", "")),
            "ip": str(res.get("target_ip", "")),
            "port": str(res.get("port", 0)),
            "protocol": str(res.get("protocol", "tcp")),
            "expected_blocked": "true" if bool(res.get("expected_blocked", False)) else "false",
        }
        reachable_val = 1 if bool(res.get("reachable", False)) else 0
        lines.append(f"vlan_probe_target_reachable{_format_labels(labels)} {reachable_val}")

    lines.extend(
        [
            "# HELP vlan_probe_target_latency_ms Measured probe latency in milliseconds.",
            "# TYPE vlan_probe_target_latency_ms gauge",
        ]
    )
    for res in results:
        latency_raw = res.get("latency_ms", 0.0)
        latency_val = float(latency_raw) if isinstance(latency_raw, (int, float)) else 0.0
        labels = {
            "vlan": str(res.get("target_vlan", "")),
            "target": str(res.get("target_name", "")),
            "ip": str(res.get("target_ip", "")),
            "port": str(res.get("port", 0)),
            "protocol": str(res.get("protocol", "tcp")),
        }
        lines.append(f"vlan_probe_target_latency_ms{_format_labels(labels)} {latency_val}")

    total_probed = _summary_int(summary, "total_probed", len(results))
    passed = _summary_int(summary, "passed", 0)
    failed = _summary_int(summary, "failed", 0)
    skipped = _summary_int(summary, "skipped", 0)

    if timestamp_seconds is None:
        timestamp_seconds = datetime.datetime.now(datetime.timezone.utc).timestamp()

    lines.extend(
        [
            "# HELP vlan_probe_targets_total Total number of configured targets probed in the latest run.",
            "# TYPE vlan_probe_targets_total gauge",
            f"vlan_probe_targets_total {total_probed}",
            "# HELP vlan_probe_targets_passed Number of targets with PASS status in the latest run.",
            "# TYPE vlan_probe_targets_passed gauge",
            f"vlan_probe_targets_passed {passed}",
            "# HELP vlan_probe_targets_failed Number of targets with FAIL (violation) status in the latest run.",
            "# TYPE vlan_probe_targets_failed gauge",
            f"vlan_probe_targets_failed {failed}",
            "# HELP vlan_probe_targets_skipped Number of targets with SKIP status in the latest run.",
            "# TYPE vlan_probe_targets_skipped gauge",
            f"vlan_probe_targets_skipped {skipped}",
            "# HELP vlan_probe_last_run_timestamp_seconds Unix timestamp (UTC) of the latest probe run.",
            "# TYPE vlan_probe_last_run_timestamp_seconds gauge",
            f"vlan_probe_last_run_timestamp_seconds {timestamp_seconds:.3f}",
        ]
    )
    return "\n".join(lines) + "\n"


def write_prometheus_textfile(prom_config: PrometheusConfig, content: str) -> None:
    """
    Atomically write Prometheus exposition content to the configured textfile path.

    Raises:
        PrometheusWriteError: On directory creation, file write, or atomic rename failure.
    """
    target_path = prom_config.textfile_path
    parent_dir = os.path.dirname(target_path)
    tmp_path = f"{target_path}.{os.getpid()}.tmp"
    try:
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, target_path)
    except Exception as e:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise PrometheusWriteError(f"Prometheus textfile write to '{target_path}' failed: {e}") from e
