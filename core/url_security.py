"""Shared outbound URL guard for ZARA's web and browser actions.

The guard is deliberately strict: research-style actions may contact only
public HTTP(S) endpoints. DNS is resolved on every validation call so callers
can revalidate each redirect instead of trusting the first hostname lookup.
"""
from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

MAX_URL_LENGTH = 4096
PUBLIC_SCHEMES = frozenset({"http", "https"})

_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
        "metadata.google",
        "metadata.azure.internal",
    }
)
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".home", ".lan")


class URLSecurityError(ValueError):
    """Raised when an outbound URL could reach a non-public destination."""


@dataclass(frozen=True)
class ValidatedPublicURL:
    """Normalized URL plus the public addresses observed during validation."""

    url: str
    host: str
    port: int
    addresses: tuple[str, ...]


def _validate_ip(address: str) -> str:
    candidate = str(address).split("%", 1)[0]
    try:
        parsed = ipaddress.ip_address(candidate)
    except ValueError as exc:
        raise URLSecurityError(f"Invalid resolved IP address: {address!r}") from exc

    mapped = getattr(parsed, "ipv4_mapped", None)
    if mapped is not None:
        parsed = mapped

    if (
        not parsed.is_global
        or parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
    ):
        raise URLSecurityError(f"Blocked non-public address: {parsed}")
    return str(parsed)


def validate_public_ip(address: str) -> str:
    """Validate a literal peer/resolver address and return its normalized form."""

    return _validate_ip(address)


def _resolver_addresses(
    host: str,
    port: int,
    resolver: Callable[..., Iterable[tuple[Any, ...]]],
) -> tuple[str, ...]:
    try:
        records = resolver(
            host,
            port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except OSError as exc:
        raise URLSecurityError(f"Could not resolve public host {host!r}: {exc}") from exc

    addresses: set[str] = set()
    for record in records:
        if len(record) < 5 or not record[4]:
            continue
        sockaddr = record[4]
        address = sockaddr[0] if isinstance(sockaddr, tuple) else str(sockaddr)
        addresses.add(_validate_ip(str(address)))

    if not addresses:
        raise URLSecurityError(f"Host {host!r} resolved to no usable address")
    return tuple(sorted(addresses))


def validate_public_http_url(
    url: str,
    *,
    resolver: Callable[..., Iterable[tuple[Any, ...]]] | None = None,
) -> ValidatedPublicURL:
    """Validate and normalize an outbound public HTTP(S) URL.

    All resolved addresses must be globally routable. Rejecting a hostname when
    *any* answer is private prevents an attacker from mixing a public answer
    with a loopback/private target.
    """

    raw = str(url or "").strip()
    if not raw:
        raise URLSecurityError("URL is required")
    if len(raw) > MAX_URL_LENGTH:
        raise URLSecurityError("URL is too long")
    if "\\" in raw or any(ord(char) < 32 or ord(char) == 127 for char in raw):
        raise URLSecurityError("URL contains unsafe characters")

    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise URLSecurityError(f"Malformed URL: {exc}") from exc

    scheme = parsed.scheme.lower()
    if scheme not in PUBLIC_SCHEMES:
        raise URLSecurityError("Only public http:// and https:// URLs are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise URLSecurityError("Credentials embedded in URLs are not allowed")

    host = parsed.hostname
    if not host:
        raise URLSecurityError("URL must include a hostname")
    if "%" in host:
        raise URLSecurityError("Scoped or escaped hostnames are not allowed")

    try:
        ascii_host = host.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise URLSecurityError("Hostname is not valid IDNA") from exc
    if not ascii_host:
        raise URLSecurityError("URL must include a hostname")
    if ascii_host in _BLOCKED_HOSTS or ascii_host.endswith(_BLOCKED_SUFFIXES):
        raise URLSecurityError(f"Blocked local or metadata hostname: {ascii_host}")

    try:
        explicit_port = parsed.port
    except ValueError as exc:
        raise URLSecurityError(f"Invalid URL port: {exc}") from exc
    port = explicit_port or (443 if scheme == "https" else 80)

    try:
        literal = ipaddress.ip_address(ascii_host)
    except ValueError:
        addresses = _resolver_addresses(ascii_host, port, resolver or socket.getaddrinfo)
    else:
        addresses = (_validate_ip(str(literal)),)

    display_host = f"[{ascii_host}]" if ":" in ascii_host else ascii_host
    netloc = display_host if explicit_port is None else f"{display_host}:{explicit_port}"
    normalized = urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))
    return ValidatedPublicURL(normalized, ascii_host, port, addresses)


def validate_connected_peer(response: object) -> None:
    """Best-effort validation of the socket peer exposed by httpx/httpcore.

    Normal httpx network streams expose ``server_addr``. Mock transports do not,
    so tests and non-network transports fall back to pre-connect DNS validation.
    Clients using this helper must disable environment proxies; otherwise the
    peer would be the proxy rather than the requested endpoint.
    """

    extensions = getattr(response, "extensions", None)
    if not isinstance(extensions, dict):
        return
    stream = extensions.get("network_stream")
    get_extra_info = getattr(stream, "get_extra_info", None)
    if not callable(get_extra_info):
        return
    try:
        peer = get_extra_info("server_addr")
    except Exception as exc:  # pragma: no cover - transport-specific defensive path
        raise URLSecurityError(f"Could not validate connected peer: {exc}") from exc
    if peer:
        address = peer[0] if isinstance(peer, tuple) else str(peer)
        _validate_ip(str(address))
