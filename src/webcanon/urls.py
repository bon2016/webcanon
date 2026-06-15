"""URL normalization and origin extraction."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_url(url: str) -> str:
    """Return a canonical form of ``url``.

    Lowercases scheme/host, drops default ports, removes fragments, and
    collapses an empty path to ``/``. This is intentionally conservative: it
    does not reorder query parameters or strip trailing slashes from non-root
    paths, since those can be semantically meaningful.
    """

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()

    netloc = host
    if parts.port is not None and parts.port != DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{parts.port}"
    if parts.username:
        userinfo = parts.username
        if parts.password:
            userinfo += f":{parts.password}"
        netloc = f"{userinfo}@{netloc}"

    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def origin_of(url: str) -> str:
    """Return ``scheme://host[:port]`` for ``url`` (no trailing slash)."""

    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    netloc = host
    if parts.port is not None and parts.port != DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{parts.port}"
    return urlunsplit((scheme, netloc, "", "", ""))


def manifest_url(origin: str, name: str) -> str:
    """Return the URL of a well-known manifest under ``origin``.

    ``name`` is one of ``robots.txt``, ``llms.txt``, ``sitemap.xml``.
    """

    return f"{origin.rstrip('/')}/{name.lstrip('/')}"
