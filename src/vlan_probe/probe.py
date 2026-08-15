"""Core VLAN probe functionality."""

import datetime
import socket
import subprocess
import time
from typing import Dict, Optional, Set

DEFAULT_TIMEOUT = 2.0


def get_local_ips() -> Set[str]:
    """Get all local IP addresses on this host."""
    ips: Set[str] = {"127.0.0.1"}
    try:
        out = subprocess.check_output(["ip", "-o", "-4", "addr", "show"], text=True, timeout=2)
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                ip = parts[3].split("/")[0]
                ips.add(ip)
    except Exception:
        try:
            hostname = socket.gethostname()
            for ip in socket.gethostbyname_ex(hostname)[2]:
                ips.add(ip)
        except Exception:
            pass
    return ips


def probe_target(
    target: Dict[str, object], timeout: float = DEFAULT_TIMEOUT, local_ips: Optional[Set[str]] = None
) -> Dict[str, object]:
    """
    Probe a single target to verify VLAN access permissions.

    Args:
        target: Dict with keys: name, vlan, ip, port, protocol, expected_blocked
        timeout: Socket timeout in seconds
        local_ips: Set of local IPs (auto-detected if None)

    Returns:
        Dict with probe result including status, latency, and error details
    """
    if local_ips is None:
        local_ips = get_local_ips()

    name = str(target.get("name", "Unknown Target"))
    vlan = str(target.get("vlan", "Unknown VLAN"))
    ip = str(target.get("ip"))
    port = int(str(target.get("port", 80)))
    protocol = str(target.get("protocol", "tcp")).lower()
    expected_blocked = bool(target.get("expected_blocked", True))

    is_self = ip in local_ips

    start_time = time.time()
    reachable = False
    error_msg: Optional[str] = None

    if protocol == "tcp":
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((ip, port))
            reachable = True
            sock.close()
        except (socket.timeout, ConnectionRefusedError, OSError):
            reachable = False
    elif protocol == "udp":
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            if port == 53:
                dns_query = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01"
                sock.sendto(dns_query, (ip, port))
            else:
                sock.sendto(b"\x00", (ip, port))
            sock.recvfrom(1024)
            reachable = True
        except socket.timeout:
            reachable = False
        except Exception:
            reachable = False
        finally:
            sock.close()

    latency_ms = round((time.time() - start_time) * 1000, 2)

    if is_self:
        passed = True
        error_details: Optional[str] = (
            f"EXEMPT_SELF_HOST: Target {ip}:{port} ({name}) is the local interface of the probing host"
        )
    elif expected_blocked:
        passed = not reachable
        if reachable:
            error_details = (
                f"UNAUTHORIZED_CONNECTIVITY_VIOLATION: Host can connect outside to "
                f"restricted VLAN '{vlan}' at {ip}:{port} ({name})"
            )
        else:
            error_details = None
    else:
        passed = reachable
        if not passed:
            error_details = f"EXPECTED_CONNECTIVITY_FAILED: Failed to connect to {name} ({ip}:{port})"
        else:
            error_details = None

    return {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "target_name": name,
        "target_vlan": vlan,
        "target_ip": ip,
        "port": port,
        "protocol": protocol,
        "reachable": reachable,
        "expected_blocked": expected_blocked,
        "status": "PASS" if passed else "FAIL",
        "latency_ms": latency_ms,
        "error": error_details or error_msg,
    }
