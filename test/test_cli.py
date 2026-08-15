"""Tests for vlan_probe.cli module."""

import json
import sys
from typing import Dict, List

import pytest

from vlan_probe.cli import (
    colorize,
    colorize_json_statuses,
    main,
    may_colorize,
    resolve_color_mode,
)
from vlan_probe.config import Config, MQTTConfig
from vlan_probe.mqtt_report import MQTTPublishError

PASS_RESULT: Dict[str, object] = {
    "timestamp": "2026-08-15T08:00:00+00:00",
    "target_name": "Device A",
    "target_vlan": "Internal",
    "target_ip": "10.0.0.1",
    "port": 22,
    "protocol": "tcp",
    "reachable": False,
    "expected_blocked": True,
    "status": "PASS",
    "latency_ms": 1.0,
    "error": None,
}

FAIL_RESULT: Dict[str, object] = {
    **PASS_RESULT,
    "status": "FAIL",
    "reachable": True,
    "error": "UNAUTHORIZED_CONNECTIVITY_VIOLATION: bad",
}


@pytest.fixture
def cli_env(monkeypatch):
    """Mock out config loading, probing and MQTT publishing."""
    sentinel = {"config": None}

    def fake_load_config(path: str) -> Config:
        return sentinel["config"]

    def fake_get_local_ips() -> set:
        return {"127.0.0.1"}

    def fake_probe_target(target, timeout, local_ips) -> Dict[str, object]:
        name = str(target.get("name"))
        if name == "FAIL":
            return FAIL_RESULT
        return PASS_RESULT

    monkeypatch.setattr("vlan_probe.cli.load_config", fake_load_config)
    monkeypatch.setattr("vlan_probe.cli.get_local_ips", fake_get_local_ips)
    monkeypatch.setattr("vlan_probe.cli.probe_target", fake_probe_target)
    return sentinel


def _run_main(monkeypatch, argv: List[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["vlan-probe"] + argv)


def test_colorize():
    assert colorize("x", "") == "x"
    assert colorize("x", "red") == "\033[31mx\033[0m"


def test_may_colorize_no_tty(monkeypatch):
    monkeypatch.setattr(sys, "stdout", sys.stderr)  # not a TTY in CI
    assert may_colorize() is False


def test_may_colorize_tty(monkeypatch):
    class FakeTty:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdout", FakeTty())
    assert may_colorize() is True
    monkeypatch.setenv("NO_COLOR", "1")
    assert may_colorize() is False


def test_resolve_color_mode():
    assert resolve_color_mode("always") is True
    assert resolve_color_mode("never") is False
    assert resolve_color_mode("auto") is False  # non-TTY


def test_colorize_json_statuses():
    line = '"status": "PASS"'
    assert colorize_json_statuses(line, False) == line
    colored = colorize_json_statuses('{"status": "PASS", "status": "FAIL"}', True)
    assert "\033[32mPASS\033[0m" in colored
    assert "\033[31mFAIL\033[0m" in colored


def test_main_ndjson(cli_env, monkeypatch, capsys):
    cli_env["config"] = Config(targets=[{"name": "PASS"}, {"name": "FAIL"}])
    _run_main(monkeypatch, ["-f", "ndjson"])
    main()
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 2
    first = json.loads(out[0])
    assert first["status"] == "PASS"
    assert first["target_name"] == "Device A"


def test_main_json(cli_env, monkeypatch, capsys):
    cli_env["config"] = Config(targets=[{"name": "PASS"}, {"name": "FAIL"}])
    _run_main(monkeypatch, ["-f", "json"])
    main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["total_probed"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["violations"][0]["target"] == "Device A"
    assert len(summary["results"]) == 2


def test_main_table(cli_env, monkeypatch, capsys):
    cli_env["config"] = Config(targets=[{"name": "PASS"}, {"name": "FAIL"}])
    _run_main(monkeypatch, ["-f", "table"])
    main()
    out = capsys.readouterr().out
    assert "VLAN" in out
    assert "Internal - Device A SSH" in out or "Internal" in out
    assert "PASS" in out and "FAIL" in out


def test_main_table_color(cli_env, monkeypatch, capsys):
    cli_env["config"] = Config(targets=[{"name": "PASS"}, {"name": "FAIL"}])
    _run_main(monkeypatch, ["-f", "table", "--color", "always"])
    main()
    out = capsys.readouterr().out
    assert "\033[36m" in out  # cyan header
    assert "\033[32m" in out  # green PASS
    assert "\033[31m" in out  # red FAIL


def test_main_strict_exits_1(cli_env, monkeypatch, capsys):
    cli_env["config"] = Config(targets=[{"name": "FAIL"}])
    _run_main(monkeypatch, ["-s", "-f", "json"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "unauthorized connection" in err


def test_main_strict_color_exits_1(cli_env, monkeypatch, capsys):
    cli_env["config"] = Config(targets=[{"name": "FAIL"}])
    _run_main(monkeypatch, ["-s", "-f", "json", "--color", "always"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "\033[1m" in err  # bold violation header
    assert "\033[31m" in err  # red violation lines


def test_main_mqtt_without_section_exits_2(cli_env, monkeypatch, capsys):
    cli_env["config"] = Config(targets=[{"name": "PASS"}])
    _run_main(monkeypatch, ["--mqtt"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    assert "[mqtt]" in capsys.readouterr().err


def test_main_mqtt_success(cli_env, monkeypatch, capsys):
    published = []
    cli_env["config"] = Config(targets=[{"name": "PASS"}], mqtt=MQTTConfig(host="broker"))
    monkeypatch.setattr("vlan_probe.cli.build_messages", lambda *a, **k: [("t", "{}")])
    monkeypatch.setattr("vlan_probe.cli.publish_to_mqtt", lambda cfg, msgs: published.append(msgs))
    _run_main(monkeypatch, ["--mqtt"])
    main()
    assert published == [[("t", "{}")]]


def test_main_mqtt_failure_exits_2(cli_env, monkeypatch, capsys):
    cli_env["config"] = Config(targets=[{"name": "PASS"}], mqtt=MQTTConfig(host="broker"))
    monkeypatch.setattr("vlan_probe.cli.build_messages", lambda *a, **k: [("t", "{}")])
    monkeypatch.setattr(
        "vlan_probe.cli.publish_to_mqtt",
        lambda cfg, msgs: (_ for _ in ()).throw(MQTTPublishError("boom")),
    )
    _run_main(monkeypatch, ["--mqtt"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    assert "MQTT: boom" in capsys.readouterr().err


def test_main_mqtt_failure_with_strict_violation_exits_1(cli_env, monkeypatch, capsys):
    cli_env["config"] = Config(targets=[{"name": "FAIL"}], mqtt=MQTTConfig(host="broker"))
    monkeypatch.setattr("vlan_probe.cli.build_messages", lambda *a, **k: [("t", "{}")])
    monkeypatch.setattr(
        "vlan_probe.cli.publish_to_mqtt",
        lambda cfg, msgs: (_ for _ in ()).throw(MQTTPublishError("boom")),
    )
    _run_main(monkeypatch, ["--mqtt", "-s"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1
