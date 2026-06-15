"""SSRF guard.

Blocks requests to non-public destinations: private/loopback/link-local IP
ranges, the cloud metadata endpoint, and non-HTTP(S) schemes. The check is run
against every URL *and* against every redirect target, after DNS resolution,
so that a public hostname resolving to a private IP is still rejected.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from .errors import SsrfError

ALLOWED_SCHEMES = frozenset({"http", "https"})


def _resolve_addresses(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:  # pragma: no cover - network dependent
        raise SsrfError(f"could not resolve host: {host}") from exc
    return [info[4][0] for info in infos]


def _is_public(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def assert_safe_url(url: str, *, block_private: bool = True) -> None:
    """Raise :class:`SsrfError` if ``url`` must not be fetched.

    When ``block_private`` is False, only the scheme is enforced (useful for
    test suites that hit ``localhost``).
    """

    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise SsrfError(f"scheme not allowed: {scheme or '(none)'}")

    host = parts.hostname
    if not host:
        raise SsrfError("URL has no host")

    if not block_private:
        return

    # A literal IP in the URL is checked directly; otherwise resolve DNS.
    try:
        ipaddress.ip_address(host)
        candidates = [host]
    except ValueError:
        candidates = _resolve_addresses(host)

    for ip_text in candidates:
        if not _is_public(ip_text):
            raise SsrfError(f"blocked non-public address: {host} -> {ip_text}")
