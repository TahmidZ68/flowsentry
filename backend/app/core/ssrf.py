from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.core.config import get_settings

# Cloud metadata ranges are NEVER permitted, even if private hosts are allowed in dev
ALWAYS_BLOCKED_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / AWS/GCP/Azure metadata
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
]

PRIVATE_AND_LOCAL_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


class SSRFValidationError(ValueError):
    """Raised when an outbound URL violates SSRF safety rules."""


def _validate_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address, allow_private: bool) -> None:
    if ip_obj.is_multicast or ip_obj.is_unspecified:
        raise SSRFValidationError(f"Blocked multicast/unspecified IP target: {ip_obj}")
    for net in ALWAYS_BLOCKED_NETWORKS:
        if ip_obj in net:
            raise SSRFValidationError(f"Blocked link-local/metadata IP target: {ip_obj}")
    if not allow_private:
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved:
            raise SSRFValidationError(f"Blocked private/loopback IP target: {ip_obj}")
        for net in PRIVATE_AND_LOCAL_NETWORKS:
            if ip_obj in net:
                raise SSRFValidationError(f"Blocked internal network IP target: {ip_obj}")


def validate_outbound_url(url: str, *, allow_private_hosts: bool | None = None) -> str:
    """
    Validate a user-supplied outbound HTTP(S) URL against SSRF attacks.

    Blocks non-HTTP(S) schemes, credentials in URL, cloud metadata IPs,
    and private/loopback networks unless explicitly permitted by config.
    """
    settings = get_settings()
    allow_private = settings.ALLOW_PRIVATE_INTEGRATION_HOSTS if allow_private_hosts is None else allow_private_hosts

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise SSRFValidationError("Only http and https URL schemes are permitted")
    if not parsed.hostname:
        raise SSRFValidationError("URL must include a valid hostname")
    if parsed.username or parsed.password:
        raise SSRFValidationError("Embedded credentials in URL are not permitted")

    hostname = parsed.hostname.lower()
    if hostname in {"metadata.google.internal", "metadata", "instance-data"}:
        raise SSRFValidationError("Blocked cloud metadata hostname")

    if not allow_private and hostname in {"localhost", "localhost.localdomain"}:
        raise SSRFValidationError("Blocked loopback hostname: localhost")

    # Direct IP literal check
    try:
        ip_literal = ipaddress.ip_address(hostname)
        _validate_ip(ip_literal, allow_private)
        return url.strip()
    except ValueError:
        pass

    # Resolve DNS to prevent DNS rebinding / internal hostname resolution
    try:
        addr_info = socket.getaddrinfo(
            hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        if allow_private:
            # Allow unresolved hostnames only if private hosts permitted? No, fail closed unless valid DNS.
            raise SSRFValidationError(f"Could not resolve hostname: {hostname}") from exc
        raise SSRFValidationError(f"Could not resolve hostname: {hostname}") from exc

    if not addr_info:
        raise SSRFValidationError(f"No DNS records found for hostname: {hostname}")

    for _, _, _, _, sockaddr in addr_info:
        resolved_ip = ipaddress.ip_address(sockaddr[0])
        _validate_ip(resolved_ip, allow_private)

    return url.strip()
