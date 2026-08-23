"""Core VLAN probe functionality."""

import datetime
import socket
import subprocess
import sys
import time
from typing import Dict, Optional, Set

DEFAULT_TIMEOUT = 2.0

_SCTP_PROTO = getattr(socket, "IPPROTO_SCTP", 132)


def get_local_ips() -> Set[str]:
    """Get all local IP addresses on this host."""
    ips: Set[str] = {"127.0.0.1", "::1"}
    detected = False
    try:
        out = subprocess.check_output(["ip", "-o", "addr", "show"], text=True, timeout=2)
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                ip = parts[3].split("/")[0]
                ip = ip.split("%")[0]
                ips.add(ip)
                detected = True
    except Exception:
        pass

    if not detected:
        try:
            hostname = socket.gethostname()
            for ip in socket.gethostbyname_ex(hostname)[2]:
                ips.add(ip)
                detected = True
        except Exception:
            pass

    if not detected:
        sys.stderr.write(
            "Warning: Failed to detect local network IP addresses; only loopback addresses will be exempted.\n"
        )

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
    port_raw = target.get("port", 80)
    port = int(port_raw) if isinstance(port_raw, (int, str)) else 80
    protocol = str(target.get("protocol", "tcp")).lower()
    expected_blocked = bool(target.get("expected_blocked", True))

    is_self = ip in local_ips

    start_time = time.time()
    reachable = False
    failure_reason: Optional[str] = None

    if protocol == "tcp":
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((ip, port))
            reachable = True
            sock.close()
        except socket.timeout:
            reachable = False
            failure_reason = "Connection timed out"
        except ConnectionRefusedError:
            reachable = False
            failure_reason = "Connection refused"
        except OSError as e:
            reachable = False
            failure_reason = f"Socket error: {e}"
    elif protocol == "udp":
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            if port == 53:
                dns_query = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01"
                sock.sendto(dns_query, (ip, port))
            elif port == 123:
                ntp_query = b"\x1b" + 47 * b"\x00"
                sock.sendto(ntp_query, (ip, port))
            else:
                sock.sendto(b"\x00", (ip, port))
            sock.recvfrom(1024)
            reachable = True
        except ConnectionRefusedError:
            reachable = False
            failure_reason = "Connection refused (ICMP Port Unreachable)"
        except socket.timeout:
            reachable = False
            failure_reason = "Timed out waiting for response"
        except OSError as e:
            reachable = False
            failure_reason = f"Socket error: {e}"
        finally:
            sock.close()
    elif protocol == "icmp":
        ping_timeout_sec = max(1, int(round(timeout)))
        try:
            completed = subprocess.run(
                ["ping", "-c", "1", "-W", str(ping_timeout_sec), ip],
                capture_output=True,
                text=True,
                timeout=timeout + 1,
            )
            reachable = completed.returncode == 0
            if not reachable:
                failure_reason = "Ping failed (no ICMP reply received)"
        except subprocess.TimeoutExpired:
            reachable = False
            failure_reason = "Ping timed out"
        except OSError as e:
            reachable = False
            failure_reason = f"Ping execution error: {e}"
    elif protocol == "sctp":
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, _SCTP_PROTO)
            sock.settimeout(timeout)
            try:
                sock.connect((ip, port))
                reachable = True
            except socket.timeout:
                reachable = False
                failure_reason = "Connection timed out"
            except ConnectionRefusedError:
                reachable = False
                failure_reason = "Connection refused"
            except OSError as e:
                reachable = False
                failure_reason = f"Socket error: {e}"
            finally:
                sock.close()
        except OSError as e:
            reachable = False
            failure_reason = f"SCTP protocol error: {e}"
    else:
        reachable = False
        failure_reason = f"Unsupported protocol '{protocol}'"

    latency_ms = round((time.time() - start_time) * 1000, 2)

    if is_self:
        status = "SKIP"
        error_details: Optional[str] = (
            f"EXEMPT_SELF_HOST: Target {ip}:{port} ({name}) is the local interface of the probing host"
        )
    elif expected_blocked:
        passed = not reachable
        status = "PASS" if passed else "FAIL"
        if reachable:
            error_details = (
                f"UNAUTHORIZED_CONNECTIVITY_VIOLATION: Host can connect outside to "
                f"restricted VLAN '{vlan}' at {ip}:{port} ({name})"
            )
        else:
            error_details = None
    else:
        passed = reachable
        status = "PASS" if passed else "FAIL"
        if not passed:
            reason_suffix = f" - {failure_reason}" if failure_reason else ""
            error_details = f"EXPECTED_CONNECTIVITY_FAILED: Failed to connect to {name} ({ip}:{port}){reason_suffix}"
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
        "status": status,
        "latency_ms": latency_ms,
        "error": error_details,
    }
