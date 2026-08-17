"""Tests for vlan_probe.cli module."""

import json
import sys
from typing import Any, Dict, List, Optional, Set

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
def cli_env(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    """Mock out config loading, probing and MQTT publishing."""
    sentinel: Dict[str, Any] = {"config": None}

    def fake_load_config(path: str) -> Config:
        cfg: Config = sentinel["config"]
        return cfg

    def fake_get_local_ips() -> Set[str]:
        return {"127.0.0.1"}

    def fake_probe_target(
        target: Dict[str, Any],
        timeout: float = 1.0,
        local_ips: Optional[Set[str]] = None,
    ) -> Dict[str, object]:
        name = str(target.get("name"))
        if name == "FAIL":
            return FAIL_RESULT
        return PASS_RESULT

    monkeypatch.setattr("vlan_probe.cli.load_config", fake_load_config)
    monkeypatch.setattr("vlan_probe.cli.get_local_ips", fake_get_local_ips)
    monkeypatch.setattr("vlan_probe.cli.probe_target", fake_probe_target)
    return sentinel


def _run_main(monkeypatch: pytest.MonkeyPatch, argv: List[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["vlan-probe"] + argv)


def test_colorize() -> None:
    assert colorize("x", "") == "x"
    assert colorize("x", "red") == "\033[31mx\033[0m"


def test_may_colorize_no_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", sys.stderr)  # not a TTY in CI
    assert may_colorize() is False


def test_may_colorize_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTty:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdout", FakeTty())
    assert may_colorize() is True
    monkeypatch.setenv("NO_COLOR", "1")
    assert may_colorize() is False


def test_resolve_color_mode() -> None:
    assert resolve_color_mode("always") is True
    assert resolve_color_mode("never") is False
    assert resolve_color_mode("auto") is False  # non-TTY


def test_colorize_json_statuses() -> None:
    line = '"status": "PASS"'
    assert colorize_json_statuses(line, False) == line
    colored = colorize_json_statuses('{"status": "PASS", "status": "FAIL"}', True)
    assert "\033[32mPASS\033[0m" in colored
    assert "\033[31mFAIL\033[0m" in colored


def test_main_ndjson(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_env["config"] = Config(targets=[{"name": "PASS"}, {"name": "FAIL"}])
    _run_main(monkeypatch, ["-f", "ndjson"])
    main()
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 2
    first = json.loads(out[0])
    assert first["status"] == "PASS"
    assert first["target_name"] == "Device A"


def test_main_json(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_env["config"] = Config(targets=[{"name": "PASS"}, {"name": "FAIL"}])
    _run_main(monkeypatch, ["-f", "json"])
    main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["total_probed"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["violations"][0]["target"] == "Device A"
    assert len(summary["results"]) == 2


def test_main_table(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_env["config"] = Config(targets=[{"name": "PASS"}, {"name": "FAIL"}])
    _run_main(monkeypatch, ["-f", "table"])
    main()
    out = capsys.readouterr().out
    assert "VLAN" in out
    assert "Internal - Device A SSH" in out or "Internal" in out
    assert "PASS" in out and "FAIL" in out


def test_main_table_color(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_env["config"] = Config(targets=[{"name": "PASS"}, {"name": "FAIL"}])
    _run_main(monkeypatch, ["-f", "table", "--color", "always"])
    main()
    out = capsys.readouterr().out
    assert "\033[36m" in out  # cyan header
    assert "\033[32m" in out  # green PASS
    assert "\033[31m" in out  # red FAIL


def test_main_strict_exits_1(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_env["config"] = Config(targets=[{"name": "FAIL"}])
    _run_main(monkeypatch, ["-s", "-f", "json"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "unauthorized connection" in err


def test_main_strict_color_exits_1(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_env["config"] = Config(targets=[{"name": "FAIL"}])
    _run_main(monkeypatch, ["-s", "-f", "json", "--color", "always"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "\033[1m" in err  # bold violation header
    assert "\033[31m" in err  # red violation lines


def test_main_mqtt_without_section_exits_2(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_env["config"] = Config(targets=[{"name": "PASS"}])
    _run_main(monkeypatch, ["--mqtt"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    assert "[mqtt]" in capsys.readouterr().err


def test_main_mqtt_success(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    published: List[Any] = []
    cli_env["config"] = Config(targets=[{"name": "PASS"}], mqtt=MQTTConfig(host="broker"))
    monkeypatch.setattr("vlan_probe.cli.build_messages", lambda *a, **k: [("t", "{}")])
    monkeypatch.setattr("vlan_probe.cli.publish_to_mqtt", lambda cfg, msgs: published.append(msgs))
    _run_main(monkeypatch, ["--mqtt", "--color", "always"])
    main()
    assert published == [[("t", "{}")]]
    out = capsys.readouterr().out
    assert "MQTT Report" in out
    assert "\033[32mPASS\033[0m" in out


def test_main_mqtt_success_json_format(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    published: List[Any] = []
    cli_env["config"] = Config(targets=[{"name": "PASS"}], mqtt=MQTTConfig(host="broker"))
    monkeypatch.setattr("vlan_probe.cli.build_messages", lambda *a, **k: [("t", "{}")])
    monkeypatch.setattr("vlan_probe.cli.publish_to_mqtt", lambda cfg, msgs: published.append(msgs))
    _run_main(monkeypatch, ["--mqtt", "-f", "json"])
    main()
    assert published == [[("t", "{}")]]
    summary = json.loads(capsys.readouterr().out)
    assert summary["mqtt"]["status"] == "PASS"
    assert summary["mqtt"]["published"] == 1


def test_main_mqtt_success_table_format(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    published: List[Any] = []
    cli_env["config"] = Config(targets=[{"name": "PASS"}], mqtt=MQTTConfig(host="broker"))
    monkeypatch.setattr("vlan_probe.cli.build_messages", lambda *a, **k: [("t", "{}")])
    monkeypatch.setattr("vlan_probe.cli.publish_to_mqtt", lambda cfg, msgs: published.append(msgs))
    _run_main(monkeypatch, ["--mqtt", "-f", "table", "--color", "always"])
    main()
    assert published == [[("t", "{}")]]
    out = capsys.readouterr().out
    assert "MQTT" in out
    assert "Published 1 msg(s)" in out


def test_main_mqtt_failure_exits_2(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_env["config"] = Config(targets=[{"name": "PASS"}], mqtt=MQTTConfig(host="broker"))
    monkeypatch.setattr("vlan_probe.cli.build_messages", lambda *a, **k: [("t", "{}")])
    monkeypatch.setattr(
        "vlan_probe.cli.publish_to_mqtt",
        lambda cfg, msgs: (_ for _ in ()).throw(MQTTPublishError("boom")),
    )
    _run_main(monkeypatch, ["--mqtt", "--color", "always"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    out = capsys.readouterr().out
    assert "MQTT Report" in out
    assert "\033[31mFAIL\033[0m" in out
    assert "boom" in out


def test_main_mqtt_failure_table_format(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_env["config"] = Config(targets=[{"name": "PASS"}], mqtt=MQTTConfig(host="broker"))
    monkeypatch.setattr("vlan_probe.cli.build_messages", lambda *a, **k: [("t", "{}")])
    monkeypatch.setattr(
        "vlan_probe.cli.publish_to_mqtt",
        lambda cfg, msgs: (_ for _ in ()).throw(MQTTPublishError("boom")),
    )
    _run_main(monkeypatch, ["--mqtt", "-f", "table", "--color", "never"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    out = capsys.readouterr().out
    assert "MQTT" in out
    assert "boom" in out


def test_main_mqtt_failure_with_strict_violation_exits_1(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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


def test_main_env_config_path(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    loaded: List[str] = []

    def recording_load_config(path: str) -> Config:
        loaded.append(path)
        cfg: Config = cli_env["config"]
        return cfg

    cli_env["config"] = Config(targets=[])
    monkeypatch.setattr("vlan_probe.cli.load_config", recording_load_config)
    monkeypatch.setenv("VLAN_PROBE_CONFIG", "/env/config.toml")
    _run_main(monkeypatch, ["-f", "json"])
    main()
    assert loaded == ["/env/config.toml"]


def test_main_env_strict_default(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_env["config"] = Config(targets=[{"name": "FAIL"}])
    monkeypatch.setenv("VLAN_PROBE_STRICT", "1")
    _run_main(monkeypatch, ["-f", "json"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1


def test_main_env_format_default(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_env["config"] = Config(targets=[{"name": "PASS"}, {"name": "FAIL"}])
    monkeypatch.setenv("VLAN_PROBE_FORMAT", "json")
    _run_main(monkeypatch, [])
    main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["total_probed"] == 2


def test_main_cli_flag_overrides_env(
    cli_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_env["config"] = Config(targets=[{"name": "PASS"}])
    monkeypatch.setenv("VLAN_PROBE_FORMAT", "json")
    _run_main(monkeypatch, ["-f", "table"])
    main()
    out = capsys.readouterr().out
    assert "VLAN" in out
    assert not out.strip().startswith("{")
