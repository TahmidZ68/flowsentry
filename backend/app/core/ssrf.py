from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpcore
import httpx

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
    if isinstance(ip_obj, ipaddress.IPv6Address):
        if ip_obj.ipv4_mapped is not None:
            _validate_ip(ip_obj.ipv4_mapped, allow_private)
            return
        if ip_obj.sixtofour is not None:
            _validate_ip(ip_obj.sixtofour, allow_private)
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


def resolve_safe_ips(hostname: str, port: int, *, allow_private: bool) -> list[str]:
    """Resolve hostname and validate every returned address against SSRF rules."""
    try:
        ip_literal = ipaddress.ip_address(hostname)
        _validate_ip(ip_literal, allow_private)
        return [str(ip_literal)]
    except ValueError:
        pass

    try:
        addr_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFValidationError(f"Could not resolve hostname: {hostname}") from exc

    if not addr_info:
        raise SSRFValidationError(f"No DNS records found for hostname: {hostname}")

    resolved_ips: list[str] = []
    for _, _, _, _, sockaddr in addr_info:
        ip_text = sockaddr[0].split("%", 1)[0]
        resolved_ip = ipaddress.ip_address(ip_text)
        _validate_ip(resolved_ip, allow_private)
        if ip_text not in resolved_ips:
            resolved_ips.append(ip_text)
    return resolved_ips


class _SSRFSafeSyncBackend(httpcore.SyncBackend):
    def __init__(self, *, allow_private_hosts: bool | None = None) -> None:
        self._allow_private_hosts = allow_private_hosts

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.NetworkStream:
        allow_private = (
            get_settings().ALLOW_PRIVATE_INTEGRATION_HOSTS
            if self._allow_private_hosts is None
            else self._allow_private_hosts
        )
        safe_ips = resolve_safe_ips(host, port, allow_private=allow_private)
        last_exc: Exception | None = None
        for safe_ip in safe_ips:
            try:
                return super().connect_tcp(
                    safe_ip,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as exc:
                last_exc = exc
        assert last_exc is not None
        raise last_exc


def build_ssrf_safe_transport(
    *,
    allow_private_hosts: bool | None = None,
    verify: bool = True,
) -> httpx.HTTPTransport:
    """Create an httpx HTTPTransport that validates DNS at connect time and pins the resolved IP."""
    transport = httpx.HTTPTransport(verify=verify, trust_env=False)
    ssl_context = getattr(transport._pool, "_ssl_context", None)
    transport._pool.close()
    transport._pool = httpcore.ConnectionPool(
        ssl_context=ssl_context,
        network_backend=_SSRFSafeSyncBackend(allow_private_hosts=allow_private_hosts),
    )
    return transport


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

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    resolve_safe_ips(hostname, port, allow_private=allow_private)
    return url.strip()
