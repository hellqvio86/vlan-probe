"""Tests for vlan_probe.prometheus_report module."""

import os
from pathlib import Path
from typing import Dict, List

import pytest

from vlan_probe.config import PrometheusConfig
from vlan_probe.prometheus_report import (
    PrometheusWriteError,
    build_prometheus_metrics,
    escape_label_value,
    write_prometheus_textfile,
)


def test_escape_label_value() -> None:
    assert escape_label_value('a\\b"c\nd') == 'a\\\\b\\"c\\nd'


def test_build_prometheus_metrics_values_and_labels() -> None:
    results: List[Dict[str, object]] = [
        {
            "target_name": 'SSH "A"',
            "target_vlan": "Internal",
            "target_ip": "10.0.0.1",
            "port": 22,
            "protocol": "tcp",
            "reachable": False,
            "expected_blocked": True,
            "status": "PASS",
            "latency_ms": 1.25,
        },
        {
            "target_name": "HTTP B",
            "target_vlan": "IoT",
            "target_ip": "10.0.2.1",
            "port": 80,
            "protocol": "tcp",
            "reachable": True,
            "expected_blocked": True,
            "status": "FAIL",
            "latency_ms": 0.5,
        },
        {
            "target_name": "Self",
            "target_vlan": "k8s",
            "target_ip": "10.0.3.1",
            "port": 0,
            "protocol": "icmp",
            "reachable": True,
            "expected_blocked": False,
            "status": "SKIP",
            "latency_ms": "invalid",
        },
    ]
    summary: Dict[str, object] = {
        "total_probed": 3,
        "passed": 1,
        "failed": 1,
        "skipped": 1,
    }
    text = build_prometheus_metrics(results=results, summary=summary, timestamp_seconds=1700000000.123)
    assert (
        'vlan_probe_target_status{vlan="Internal",target="SSH \\"A\\"",'
        'ip="10.0.0.1",port="22",protocol="tcp",expected_blocked="true"} 1'
    ) in text
    assert (
        'vlan_probe_target_status{vlan="IoT",target="HTTP B",'
        'ip="10.0.2.1",port="80",protocol="tcp",expected_blocked="true"} 0'
    ) in text
    assert (
        'vlan_probe_target_status{vlan="k8s",target="Self",'
        'ip="10.0.3.1",port="0",protocol="icmp",expected_blocked="false"} -1'
    ) in text
    assert (
        'vlan_probe_target_reachable{vlan="Internal",target="SSH \\"A\\"",'
        'ip="10.0.0.1",port="22",protocol="tcp",expected_blocked="true"} 0'
    ) in text
    assert (
        'vlan_probe_target_reachable{vlan="IoT",target="HTTP B",'
        'ip="10.0.2.1",port="80",protocol="tcp",expected_blocked="true"} 1'
    ) in text
    assert (
        'vlan_probe_target_latency_ms{vlan="Internal",target="SSH \\"A\\"",ip="10.0.0.1",port="22",protocol="tcp"} 1.25'
    ) in text
    assert 'vlan_probe_target_latency_ms{vlan="k8s",target="Self",ip="10.0.3.1",port="0",protocol="icmp"} 0.0' in text
    assert "vlan_probe_targets_total 3" in text
    assert "vlan_probe_targets_passed 1" in text
    assert "vlan_probe_targets_failed 1" in text
    assert "vlan_probe_targets_skipped 1" in text
    assert "vlan_probe_last_run_timestamp_seconds 1700000000.123" in text
    assert text.endswith("\n")


def test_build_prometheus_metrics_default_timestamp_and_empty_summary() -> None:
    text = build_prometheus_metrics(results=[], summary={})
    assert "vlan_probe_targets_total 0" in text
    assert "vlan_probe_targets_passed 0" in text
    assert "vlan_probe_targets_failed 0" in text
    assert "vlan_probe_targets_skipped 0" in text
    assert "vlan_probe_last_run_timestamp_seconds " in text


def test_write_prometheus_textfile_success(tmp_path: Path) -> None:
    prom_file = tmp_path / "subdir" / "vlan_probe.prom"
    cfg = PrometheusConfig(textfile_path=str(prom_file))
    write_prometheus_textfile(prom_config=cfg, content="# metric 1\n")
    assert prom_file.read_text(encoding="utf-8") == "# metric 1\n"
    assert (prom_file.stat().st_mode & 0o777) == 0o644


def test_write_prometheus_textfile_relative_filename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = PrometheusConfig(textfile_path="local.prom")
    write_prometheus_textfile(prom_config=cfg, content="# local\n")
    assert (tmp_path / "local.prom").read_text(encoding="utf-8") == "# local\n"


def test_write_prometheus_textfile_replace_error_cleans_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prom_file = tmp_path / "vlan_probe.prom"
    cfg = PrometheusConfig(textfile_path=str(prom_file))

    def boom_replace(src: str, dst: str) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("vlan_probe.prometheus_report.os.replace", boom_replace)
    with pytest.raises(PrometheusWriteError, match="replace failed"):
        write_prometheus_textfile(prom_config=cfg, content="# test\n")

    tmp_candidate = Path(f"{prom_file}.{os.getpid()}.tmp")
    assert not tmp_candidate.exists()


def test_write_prometheus_textfile_cleanup_unlink_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prom_file = tmp_path / "vlan_probe.prom"
    cfg = PrometheusConfig(textfile_path=str(prom_file))

    def boom_replace(src: str, dst: str) -> None:
        raise OSError("replace failed")

    def boom_unlink(path: str) -> None:
        raise OSError("unlink failed")

    monkeypatch.setattr("vlan_probe.prometheus_report.os.replace", boom_replace)
    monkeypatch.setattr("vlan_probe.prometheus_report.os.unlink", boom_unlink)
    with pytest.raises(PrometheusWriteError, match="replace failed"):
        write_prometheus_textfile(prom_config=cfg, content="# test\n")
