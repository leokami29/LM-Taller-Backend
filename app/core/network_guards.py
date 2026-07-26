"""Validaciones contra SSRF y destinos de red no seguros."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
    }
)

_ALLOWED_SMTP_PORTS = frozenset({25, 465, 587, 2525})
_MAX_LOGO_BYTES = 2 * 1024 * 1024


def _is_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def resolve_hostname_is_public(hostname: str) -> None:
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        raise ValueError("Host vacío")
    if host in _BLOCKED_HOSTNAMES or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("Host no permitido")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if _is_unsafe_ip(ip):
            raise ValueError("Dirección IP no permitida")
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError("No se pudo resolver el host") from exc
    if not infos:
        raise ValueError("No se pudo resolver el host")
    for info in infos:
        sockaddr = info[4]
        try:
            resolved = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if _is_unsafe_ip(resolved):
            raise ValueError("El host resuelve a una red privada o reservada")


def validate_public_https_url(url: str) -> str:
    raw = (url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https":
        raise ValueError("Solo se permiten URLs https")
    if parsed.username or parsed.password:
        raise ValueError("URL con credenciales no permitida")
    if not parsed.hostname:
        raise ValueError("URL sin host")
    resolve_hostname_is_public(parsed.hostname)
    return raw


def validate_logo_reference(logo_url: str | None) -> str | None:
    if logo_url is None:
        return None
    value = logo_url.strip()
    if not value:
        return None
    if value.startswith("data:"):
        if "," not in value:
            raise ValueError("data URI de logo inválida")
        header, encoded = value.split(",", 1)
        mime = header[5:].split(";")[0].strip().lower()
        if mime not in {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"}:
            raise ValueError("MIME de logo no permitido")
        # Rough size bound without full decode cost in admin path.
        if len(encoded) > (_MAX_LOGO_BYTES * 4) // 3 + 64:
            raise ValueError("Logo demasiado grande")
        return value
    return validate_public_https_url(value)


def validate_smtp_endpoint(host: str | None, port: int | None) -> tuple[str | None, int]:
    if not host or not str(host).strip():
        return None, port or 587
    hostname = str(host).strip()
    resolved_port = int(port or 587)
    if resolved_port not in _ALLOWED_SMTP_PORTS:
        raise ValueError("Puerto SMTP no permitido")
    resolve_hostname_is_public(hostname)
    return hostname, resolved_port


__all__ = [
    "validate_logo_reference",
    "validate_public_https_url",
    "validate_smtp_endpoint",
    "resolve_hostname_is_public",
    "_MAX_LOGO_BYTES",
]
