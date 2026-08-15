"""
VLAN Isolation & Network Permission Probe Tool.

Probes target VLAN subnets, IPs, and ports from the host environment to verify
isolation policies and detect unauthorized inter-VLAN access violations.
"""

__version__ = "0.1.0"
__all__ = ["probe_target", "get_local_ips"]

from .probe import get_local_ips, probe_target
