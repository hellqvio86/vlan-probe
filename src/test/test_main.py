"""Tests for module entrypoint guards (``if __name__ == "__main__"``)."""

import runpy
import sys

import pytest


@pytest.mark.parametrize("module", ["vlan_probe.cli", "vlan_probe.__main__"])
def test_module_entrypoint(module: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running the modules as scripts invokes the CLI against a missing config."""
    monkeypatch.setattr(sys, "argv", ["vlan-probe", "-c", "/nonexistent/vlan_probe.toml"])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module(module, run_name="__main__")
    assert excinfo.value.code == 2
