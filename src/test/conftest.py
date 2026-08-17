"""Conftest for pytest fixtures."""

import sys
from pathlib import Path

# Add src directory to path so imports work
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

import pytest  # noqa: E402

from vlan_probe.config import ALL_ENV_VARS  # noqa: E402


@pytest.fixture(autouse=True)
def clean_vlan_probe_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove VLAN_PROBE_* env vars so tests start from a known state."""
    for var in ALL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
